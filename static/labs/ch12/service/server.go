package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
)

type contextKey string

const traceContextKey contextKey = "trace-id"

var (
	tokenPattern = regexp.MustCompile(
		`^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`,
	)
	skuPattern = regexp.MustCompile(
		`^[A-Z0-9][A-Z0-9._-]{2,31}$`,
	)
)

type apiServer struct {
	store         *store
	metrics       *serviceMetrics
	logger        *slog.Logger
	faultsEnabled bool
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (writer *statusRecorder) WriteHeader(status int) {
	if writer.status != 0 {
		return
	}
	writer.status = status
	writer.ResponseWriter.WriteHeader(status)
}

func (writer *statusRecorder) Write(body []byte) (int, error) {
	if writer.status == 0 {
		writer.WriteHeader(http.StatusOK)
	}
	return writer.ResponseWriter.Write(body)
}

func (api *apiServer) handler() http.Handler {
	mux := http.NewServeMux()
	mux.Handle(
		"GET /health/live",
		api.route("health.live", api.live),
	)
	mux.Handle(
		"GET /health/ready",
		api.route("health.ready", api.ready),
	)
	mux.Handle(
		"GET /metrics",
		api.route("metrics", api.serveMetrics),
	)
	mux.Handle(
		"POST /v1/orders",
		api.route("orders.create", api.createOrder),
	)
	mux.Handle(
		"GET /v1/orders",
		api.route("orders.list", api.listOrders),
	)
	mux.Handle(
		"GET /v1/orders/{orderID}",
		api.route("orders.get", api.getOrder),
	)
	mux.Handle(
		"POST /v1/payments",
		api.route("payments.capture", api.capturePayment),
	)
	mux.Handle(
		"GET /debug/hold",
		api.route("debug.hold", api.debugHold),
	)
	return mux
}

func (api *apiServer) route(
	route string,
	next http.HandlerFunc,
) http.Handler {
	return http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		started := time.Now()
		recorder := &statusRecorder{ResponseWriter: writer}
		traceID := request.Header.Get("X-Request-ID")
		if !tokenPattern.MatchString(traceID) {
			traceID = randomTraceID()
		}
		writer.Header().Set("X-Request-ID", traceID)

		ctx := context.WithValue(
			request.Context(),
			traceContextKey,
			traceID,
		)
		var cancel context.CancelFunc
		if api.faultsEnabled {
			if raw := request.Header.Get(
				"X-PG36-Deadline-Ms",
			); raw != "" {
				milliseconds, err := strconv.Atoi(raw)
				if err != nil ||
					milliseconds < 10 ||
					milliseconds > 5000 {
					api.writeError(
						recorder,
						request.WithContext(ctx),
						&apiError{
							HTTPStatus: 400,
							Code:       "invalid_deadline",
							Message:    "lab deadline must be between 10 and 5000 ms",
							Retryable:  false,
						},
					)
					api.finishRequest(
						route,
						traceID,
						started,
						recorder,
					)
					return
				}
				ctx, cancel = context.WithTimeout(
					ctx,
					time.Duration(milliseconds)*time.Millisecond,
				)
				defer cancel()
			}
		}
		request = request.WithContext(ctx)
		next(recorder, request)
		api.finishRequest(route, traceID, started, recorder)
	})
}

func (api *apiServer) finishRequest(
	route string,
	traceID string,
	started time.Time,
	recorder *statusRecorder,
) {
	status := recorder.status
	if status == 0 {
		status = http.StatusOK
	}
	duration := time.Since(started)
	api.metrics.observeRequest(route, status, duration)
	api.logger.Info(
		"request",
		"route", route,
		"status", status,
		"duration_ms", float64(duration.Microseconds())/1000,
		"trace_id", traceID,
	)
}

func randomTraceID() string {
	buffer := make([]byte, 8)
	if _, err := rand.Read(buffer); err != nil {
		return fmt.Sprintf("generated-%d", time.Now().UnixNano())
	}
	return "generated-" + hex.EncodeToString(buffer)
}

func traceID(ctx context.Context) string {
	value, _ := ctx.Value(traceContextKey).(string)
	return value
}

func (api *apiServer) live(
	writer http.ResponseWriter,
	request *http.Request,
) {
	api.writeJSON(writer, http.StatusOK, map[string]string{
		"status": "ok",
	})
}

func (api *apiServer) ready(
	writer http.ResponseWriter,
	request *http.Request,
) {
	ctx, cancel := context.WithTimeout(
		request.Context(),
		150*time.Millisecond,
	)
	defer cancel()
	details, err := api.store.readiness(ctx)
	if err != nil {
		api.writeError(writer, request, err)
		return
	}
	api.writeJSON(writer, http.StatusOK, details)
}

func (api *apiServer) serveMetrics(
	writer http.ResponseWriter,
	request *http.Request,
) {
	writer.Header().Set(
		"Content-Type",
		"text/plain; version=0.0.4; charset=utf-8",
	)
	writer.WriteHeader(http.StatusOK)
	api.metrics.render(writer, api.store.pool)
}

func (api *apiServer) createOrder(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var input createOrderRequest
	if err := decodeJSON(writer, request, &input); err != nil {
		api.writeError(writer, request, err)
		return
	}
	if !tokenPattern.MatchString(input.RequestKey) ||
		!tokenPattern.MatchString(input.CustomerRef) ||
		!skuPattern.MatchString(input.SKU) ||
		input.Quantity < 1 ||
		input.Quantity > 1000 {
		api.writeError(writer, request, &apiError{
			HTTPStatus: 400,
			Code:       "invalid_order",
			Message:    "order fields violate the API contract",
			Retryable:  false,
		})
		return
	}

	fault := request.Header.Get("X-PG36-Fault")
	if fault != "" {
		if !api.faultsEnabled ||
			(fault != "statement-timeout" &&
				fault != "retry-once") {
			api.writeError(writer, request, &apiError{
				HTTPStatus: 400,
				Code:       "invalid_fault",
				Message:    "fault injection is disabled or unknown",
				Retryable:  false,
			})
			return
		}
	}

	response, replayed, err := api.store.createOrder(
		request.Context(),
		input,
		traceID(request.Context()),
		fault,
	)
	if err != nil {
		api.writeError(writer, request, err)
		return
	}
	if replayed {
		writer.Header().Set("Idempotency-Replayed", "true")
	}
	api.writeJSON(writer, http.StatusCreated, response)
}

func (api *apiServer) capturePayment(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var input capturePaymentRequest
	if err := decodeJSON(writer, request, &input); err != nil {
		api.writeError(writer, request, err)
		return
	}
	if !tokenPattern.MatchString(input.IdempotencyKey) ||
		input.OrderID <= 0 ||
		input.AmountMinor <= 0 {
		api.writeError(writer, request, &apiError{
			HTTPStatus: 400,
			Code:       "invalid_payment",
			Message:    "payment fields violate the API contract",
			Retryable:  false,
		})
		return
	}

	response, replayed, err := api.store.capturePayment(
		request.Context(),
		input,
		traceID(request.Context()),
	)
	if err != nil {
		api.writeError(writer, request, err)
		return
	}
	if replayed {
		writer.Header().Set("Idempotency-Replayed", "true")
	}
	api.writeJSON(writer, http.StatusCreated, response)
}

func (api *apiServer) getOrder(
	writer http.ResponseWriter,
	request *http.Request,
) {
	orderID, err := strconv.ParseInt(
		request.PathValue("orderID"),
		10,
		64,
	)
	if err != nil || orderID <= 0 {
		api.writeError(writer, request, &apiError{
			HTTPStatus: 400,
			Code:       "invalid_order_id",
			Message:    "order id must be a positive integer",
			Retryable:  false,
		})
		return
	}
	view, err := api.store.getOrder(
		request.Context(),
		orderID,
	)
	if err != nil {
		api.writeError(writer, request, err)
		return
	}
	api.writeJSON(writer, http.StatusOK, view)
}

func (api *apiServer) listOrders(
	writer http.ResponseWriter,
	request *http.Request,
) {
	after := int64(0)
	limit := int64(20)
	var err error
	if raw := request.URL.Query().Get("after"); raw != "" {
		after, err = strconv.ParseInt(raw, 10, 64)
		if err != nil || after < 0 {
			api.writeError(writer, request, &apiError{
				HTTPStatus: 400,
				Code:       "invalid_cursor",
				Message:    "after cursor must be a non-negative integer",
				Retryable:  false,
			})
			return
		}
	}
	if raw := request.URL.Query().Get("limit"); raw != "" {
		limit, err = strconv.ParseInt(raw, 10, 32)
		if err != nil || limit < 1 || limit > 100 {
			api.writeError(writer, request, &apiError{
				HTTPStatus: 400,
				Code:       "invalid_limit",
				Message:    "limit must be between 1 and 100",
				Retryable:  false,
			})
			return
		}
	}
	page, err := api.store.listOrders(
		request.Context(),
		after,
		int32(limit),
	)
	if err != nil {
		api.writeError(writer, request, err)
		return
	}
	api.writeJSON(writer, http.StatusOK, page)
}

func (api *apiServer) debugHold(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if !api.faultsEnabled {
		api.writeError(writer, request, &apiError{
			HTTPStatus: 404,
			Code:       "not_found",
			Message:    "resource not found",
			Retryable:  false,
		})
		return
	}
	milliseconds, err := strconv.Atoi(
		request.URL.Query().Get("ms"),
	)
	if err != nil || milliseconds < 1 || milliseconds > 3000 {
		api.writeError(writer, request, &apiError{
			HTTPStatus: 400,
			Code:       "invalid_hold",
			Message:    "hold duration must be between 1 and 3000 ms",
			Retryable:  false,
		})
		return
	}
	if err := api.store.hold(
		request.Context(),
		time.Duration(milliseconds)*time.Millisecond,
	); err != nil {
		api.writeError(writer, request, err)
		return
	}
	api.writeJSON(writer, http.StatusOK, map[string]any{
		"status":  "released",
		"held_ms": milliseconds,
	})
}

func decodeJSON(
	writer http.ResponseWriter,
	request *http.Request,
	target any,
) error {
	request.Body = http.MaxBytesReader(
		writer,
		request.Body,
		64*1024,
	)
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return &apiError{
			HTTPStatus: 400,
			Code:       "invalid_json",
			Message:    "request body must be one valid JSON object",
			Retryable:  false,
			Cause:      err,
		}
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return &apiError{
			HTTPStatus: 400,
			Code:       "invalid_json",
			Message:    "request body must contain exactly one JSON value",
			Retryable:  false,
		}
	}
	return nil
}

func (api *apiServer) writeError(
	writer http.ResponseWriter,
	request *http.Request,
	err error,
) {
	mapped := mapDatabaseError(err)
	var responseError *apiError
	if !errors.As(mapped, &responseError) {
		responseError = &apiError{
			HTTPStatus: 500,
			Code:       "internal_error",
			Message:    "internal service error",
			Retryable:  false,
			Cause:      mapped,
		}
	}
	if responseError.SQLState != "" {
		api.metrics.observeDBError(responseError.SQLState)
	}

	fields := []any{
		"error_code", responseError.Code,
		"status", responseError.HTTPStatus,
		"retryable", responseError.Retryable,
		"trace_id", traceID(request.Context()),
	}
	var databaseError *pgconn.PgError
	if errors.As(responseError, &databaseError) {
		fields = append(
			fields,
			"sqlstate", databaseError.Code,
			"constraint", databaseError.ConstraintName,
		)
	}
	api.logger.Warn("request_error", fields...)

	api.writeJSON(
		writer,
		responseError.HTTPStatus,
		errorEnvelope{Error: errorBody{
			Code:      responseError.Code,
			Message:   responseError.Message,
			Retryable: responseError.Retryable,
			TraceID:   traceID(request.Context()),
		}},
	)
}

func (api *apiServer) writeJSON(
	writer http.ResponseWriter,
	status int,
	value any,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(true)
	if err := encoder.Encode(value); err != nil {
		api.logger.Error(
			"encode_response",
			"error", strings.TrimSpace(err.Error()),
		)
	}
}
