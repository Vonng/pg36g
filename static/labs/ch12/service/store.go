package main

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type store struct {
	pool    *pgxpool.Pool
	metrics *serviceMetrics
}

func newStore(
	ctx context.Context,
	databaseURL string,
	maxConns int32,
	minIdleConns int32,
	metrics *serviceMetrics,
) (*store, error) {
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database configuration: %w", err)
	}

	config.MaxConns = maxConns
	config.MinConns = 0
	config.MinIdleConns = minIdleConns
	config.MaxConnLifetime = 30 * time.Minute
	config.MaxConnLifetimeJitter = 3 * time.Minute
	config.MaxConnIdleTime = 5 * time.Minute
	config.HealthCheckPeriod = 30 * time.Second
	config.PingTimeout = 2 * time.Second
	config.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeExec
	config.ConnConfig.RuntimeParams["application_name"] =
		"pg36-ch12-api"

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("construct database pool: %w", err)
	}

	pingContext, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if err := pool.Ping(pingContext); err != nil {
		pool.Close()
		return nil, fmt.Errorf("initial database ping: %w", err)
	}

	return &store{pool: pool, metrics: metrics}, nil
}

func fingerprint(parts ...string) string {
	hasher := sha256.New()
	var length [8]byte
	for _, part := range parts {
		binary.BigEndian.PutUint64(
			length[:],
			uint64(len(part)),
		)
		_, _ = hasher.Write(length[:])
		_, _ = hasher.Write([]byte(part))
	}
	return hex.EncodeToString(hasher.Sum(nil))
}

func (s *store) withTransactionRetry(
	ctx context.Context,
	maxAttempts int,
	work func(pgx.Tx) error,
) error {
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		connection, err := s.pool.Acquire(ctx)
		if err != nil {
			return poolAcquireError(err)
		}

		transaction, err := connection.BeginTx(
			ctx,
			pgx.TxOptions{IsoLevel: pgx.ReadCommitted},
		)
		if err != nil {
			connection.Release()
			return mapDatabaseError(err)
		}

		workErr := work(transaction)
		if workErr == nil {
			workErr = transaction.Commit(ctx)
		} else {
			rollbackContext, cancel := context.WithTimeout(
				context.Background(),
				time.Second,
			)
			_ = transaction.Rollback(rollbackContext)
			cancel()
		}
		connection.Release()

		if workErr == nil {
			return nil
		}
		if !isRetryableTransactionError(workErr) ||
			attempt == maxAttempts {
			return mapDatabaseError(workErr)
		}

		var databaseError *pgconn.PgError
		if errors.As(workErr, &databaseError) {
			s.metrics.observeDBError(databaseError.Code)
		}
		s.metrics.transactionRetries.Add(1)
		timer := time.NewTimer(
			time.Duration(attempt*10) * time.Millisecond,
		)
		select {
		case <-ctx.Done():
			timer.Stop()
			return mapDatabaseError(ctx.Err())
		case <-timer.C:
		}
	}
	return &apiError{
		HTTPStatus: 503,
		Code:       "transaction_retry_exhausted",
		Message:    "database transaction retry budget exhausted",
		Retryable:  true,
	}
}

func (s *store) createOrder(
	ctx context.Context,
	request createOrderRequest,
	traceID string,
	fault string,
) (orderResponse, bool, error) {
	requestFingerprint := fingerprint(
		request.CustomerRef,
		request.SKU,
		fmt.Sprintf("%d", request.Quantity),
	)
	var response orderResponse
	replayed := false

	err := s.withTransactionRetry(
		ctx,
		3,
		func(transaction pgx.Tx) error {
			if fault == "retry-once" {
				if _, err := transaction.Exec(
					ctx,
					`SELECT shop_ch12.raise_serialization_once()`,
				); err != nil {
					return err
				}
			}
			if fault == "statement-timeout" {
				if _, err := transaction.Exec(
					ctx,
					`SET LOCAL statement_timeout = '50ms'`,
				); err != nil {
					return err
				}
				if _, err := transaction.Exec(
					ctx,
					`SELECT pg_catalog.pg_sleep(0.2)`,
				); err != nil {
					return err
				}
			}

			commandTag, err := transaction.Exec(
				ctx,
				`
				INSERT INTO shop_ch12.order_request (
				    request_key,
				    fingerprint
				)
				VALUES ($1, $2)
				ON CONFLICT (request_key) DO NOTHING
				`,
				request.RequestKey,
				requestFingerprint,
			)
			if err != nil {
				return err
			}

			if commandTag.RowsAffected() == 0 {
				var storedFingerprint string
				var storedResponse []byte
				err = transaction.QueryRow(
					ctx,
					`
					SELECT fingerprint, response
					FROM shop_ch12.order_request
					WHERE request_key = $1
					FOR UPDATE
					`,
					request.RequestKey,
				).Scan(&storedFingerprint, &storedResponse)
				if err != nil {
					return err
				}
				if storedFingerprint != requestFingerprint {
					return &apiError{
						HTTPStatus: 409,
						Code:       "idempotency_conflict",
						Message:    "request key was already used with a different payload",
						Retryable:  false,
					}
				}
				if len(storedResponse) == 0 {
					return &apiError{
						HTTPStatus: 500,
						Code:       "idempotency_incomplete",
						Message:    "committed idempotency record has no response",
						Retryable:  false,
					}
				}
				response, err = decodeJSONBytes[orderResponse](
					storedResponse,
				)
				if err != nil {
					return &apiError{
						HTTPStatus: 500,
						Code:       "stored_response_invalid",
						Message:    "stored order response is invalid",
						Retryable:  false,
						Cause:      err,
					}
				}
				replayed = true
				return nil
			}

			var unitPrice int64
			var currency string
			var available int32
			err = transaction.QueryRow(
				ctx,
				`
				UPDATE shop_ch12.inventory
				SET available = available - $2,
				    version = version + 1
				WHERE sku = $1
				  AND available >= $2
				RETURNING
				    unit_price_minor,
				    currency_code,
				    available
				`,
				request.SKU,
				request.Quantity,
			).Scan(&unitPrice, &currency, &available)
			if errors.Is(err, pgx.ErrNoRows) {
				var currentAvailable int32
				lookupErr := transaction.QueryRow(
					ctx,
					`
					SELECT available
					FROM shop_ch12.inventory
					WHERE sku = $1
					`,
					request.SKU,
				).Scan(&currentAvailable)
				if errors.Is(lookupErr, pgx.ErrNoRows) {
					return &apiError{
						HTTPStatus: 404,
						Code:       "sku_not_found",
						Message:    "inventory item does not exist",
						Retryable:  false,
					}
				}
				if lookupErr != nil {
					return lookupErr
				}
				return &apiError{
					HTTPStatus: 409,
					Code:       "insufficient_inventory",
					Message:    "requested quantity is unavailable",
					Retryable:  false,
				}
			}
			if err != nil {
				return err
			}

			totalMinor := unitPrice * int64(request.Quantity)
			err = transaction.QueryRow(
				ctx,
				`
				INSERT INTO shop_ch12.sales_order (
				    customer_ref,
				    state,
				    total_minor,
				    currency_code,
				    trace_id
				)
				VALUES ($1, 'placed', $2, $3, $4)
				RETURNING order_id
				`,
				request.CustomerRef,
				totalMinor,
				currency,
				traceID,
			).Scan(&response.OrderID)
			if err != nil {
				return err
			}

			response.State = "placed"
			response.TotalMinor = totalMinor
			response.CurrencyCode = currency

			if _, err = transaction.Exec(
				ctx,
				`
				INSERT INTO shop_ch12.sales_order_item (
				    order_id,
				    line_no,
				    sku,
				    quantity,
				    unit_price_minor
				)
				VALUES ($1, 1, $2, $3, $4)
				`,
				response.OrderID,
				request.SKU,
				request.Quantity,
				unitPrice,
			); err != nil {
				return err
			}

			payload, err := json.Marshal(response)
			if err != nil {
				return err
			}
			if _, err = transaction.Exec(
				ctx,
				`
				INSERT INTO shop_ch12.outbox (
				    event_key,
				    aggregate_type,
				    aggregate_id,
				    event_type,
				    payload,
				    trace_id
				)
				VALUES (
				    $1,
				    'order',
				    $2,
				    'order.placed',
				    $3,
				    $4
				)
				`,
				"order:"+request.RequestKey+":placed",
				response.OrderID,
				string(payload),
				traceID,
			); err != nil {
				return err
			}

			commandTag, err = transaction.Exec(
				ctx,
				`
				UPDATE shop_ch12.order_request
				SET order_id = $2,
				    response = $3
				WHERE request_key = $1
				`,
				request.RequestKey,
				response.OrderID,
				string(payload),
			)
			_ = available
			return requireOneRow(
				commandTag,
				err,
				"complete order request",
			)
		},
	)
	if err != nil {
		return orderResponse{}, false, err
	}
	if replayed {
		s.metrics.idempotentReplays.Add(1)
	}
	return response, replayed, nil
}

func (s *store) capturePayment(
	ctx context.Context,
	request capturePaymentRequest,
	traceID string,
) (paymentResponse, bool, error) {
	requestFingerprint := fingerprint(
		fmt.Sprintf("%d", request.OrderID),
		fmt.Sprintf("%d", request.AmountMinor),
	)
	var response paymentResponse
	replayed := false

	err := s.withTransactionRetry(
		ctx,
		3,
		func(transaction pgx.Tx) error {
			commandTag, err := transaction.Exec(
				ctx,
				`
				INSERT INTO shop_ch12.payment_request (
				    idempotency_key,
				    fingerprint
				)
				VALUES ($1, $2)
				ON CONFLICT (idempotency_key) DO NOTHING
				`,
				request.IdempotencyKey,
				requestFingerprint,
			)
			if err != nil {
				return err
			}

			if commandTag.RowsAffected() == 0 {
				var storedFingerprint string
				var storedResponse []byte
				err = transaction.QueryRow(
					ctx,
					`
					SELECT fingerprint, response
					FROM shop_ch12.payment_request
					WHERE idempotency_key = $1
					FOR UPDATE
					`,
					request.IdempotencyKey,
				).Scan(&storedFingerprint, &storedResponse)
				if err != nil {
					return err
				}
				if storedFingerprint != requestFingerprint {
					return &apiError{
						HTTPStatus: 409,
						Code:       "idempotency_conflict",
						Message:    "idempotency key was already used with a different payload",
						Retryable:  false,
					}
				}
				if len(storedResponse) == 0 {
					return &apiError{
						HTTPStatus: 500,
						Code:       "idempotency_incomplete",
						Message:    "committed idempotency record has no response",
						Retryable:  false,
					}
				}
				response, err =
					decodeJSONBytes[paymentResponse](storedResponse)
				if err != nil {
					return &apiError{
						HTTPStatus: 500,
						Code:       "stored_response_invalid",
						Message:    "stored payment response is invalid",
						Retryable:  false,
						Cause:      err,
					}
				}
				replayed = true
				return nil
			}

			var orderState string
			var totalMinor int64
			var currency string
			err = transaction.QueryRow(
				ctx,
				`
				SELECT state, total_minor, currency_code
				FROM shop_ch12.sales_order
				WHERE order_id = $1
				FOR UPDATE
				`,
				request.OrderID,
			).Scan(&orderState, &totalMinor, &currency)
			if errors.Is(err, pgx.ErrNoRows) {
				return &apiError{
					HTTPStatus: 404,
					Code:       "order_not_found",
					Message:    "order does not exist",
					Retryable:  false,
				}
			}
			if err != nil {
				return err
			}
			if orderState == "paid" {
				return &apiError{
					HTTPStatus: 409,
					Code:       "already_paid",
					Message:    "order already has a captured payment",
					Retryable:  false,
				}
			}
			if totalMinor != request.AmountMinor {
				return &apiError{
					HTTPStatus: 422,
					Code:       "amount_mismatch",
					Message:    "payment amount does not match order total",
					Retryable:  false,
				}
			}

			err = transaction.QueryRow(
				ctx,
				`
				INSERT INTO shop_ch12.payment (
				    order_id,
				    amount_minor,
				    currency_code,
				    state,
				    trace_id
				)
				VALUES ($1, $2, $3, 'captured', $4)
				RETURNING payment_id
				`,
				request.OrderID,
				request.AmountMinor,
				currency,
				traceID,
			).Scan(&response.PaymentID)
			if err != nil {
				return err
			}
			response.OrderID = request.OrderID
			response.State = "captured"
			response.AmountMinor = request.AmountMinor
			response.Currency = currency

			commandTag, err = transaction.Exec(
				ctx,
				`
				UPDATE shop_ch12.sales_order
				SET state = 'paid'
				WHERE order_id = $1
				  AND state = 'placed'
				`,
				request.OrderID,
			)
			if err := requireOneRow(
				commandTag,
				err,
				"mark order paid",
			); err != nil {
				return err
			}

			payload, err := json.Marshal(response)
			if err != nil {
				return err
			}
			if _, err = transaction.Exec(
				ctx,
				`
				INSERT INTO shop_ch12.outbox (
				    event_key,
				    aggregate_type,
				    aggregate_id,
				    event_type,
				    payload,
				    trace_id
				)
				VALUES (
				    $1,
				    'payment',
				    $2,
				    'payment.captured',
				    $3,
				    $4
				)
				`,
				"payment:"+request.IdempotencyKey+":captured",
				response.PaymentID,
				string(payload),
				traceID,
			); err != nil {
				return err
			}

			commandTag, err = transaction.Exec(
				ctx,
				`
				UPDATE shop_ch12.payment_request
				SET payment_id = $2,
				    response = $3
				WHERE idempotency_key = $1
				`,
				request.IdempotencyKey,
				response.PaymentID,
				string(payload),
			)
			return requireOneRow(
				commandTag,
				err,
				"complete payment request",
			)
		},
	)
	if err != nil {
		return paymentResponse{}, false, err
	}
	if replayed {
		s.metrics.idempotentReplays.Add(1)
	}
	return response, replayed, nil
}

func (s *store) getOrder(
	ctx context.Context,
	orderID int64,
) (orderView, error) {
	connection, err := s.pool.Acquire(ctx)
	if err != nil {
		return orderView{}, poolAcquireError(err)
	}
	defer connection.Release()

	var view orderView
	var itemJSON []byte
	var paymentJSON []byte
	err = connection.QueryRow(
		ctx,
		`
		SELECT
		    orders.order_id,
		    orders.customer_ref,
		    orders.state,
		    orders.total_minor,
		    orders.currency_code,
		    orders.trace_id,
		    orders.created_at,
		    items.value,
		    payment.value
		FROM shop_ch12.sales_order AS orders
		CROSS JOIN LATERAL (
		    SELECT COALESCE(
		        pg_catalog.jsonb_agg(
		            pg_catalog.jsonb_build_object(
		                'line_no', line.line_no,
		                'sku', line.sku,
		                'quantity', line.quantity,
		                'unit_price_minor', line.unit_price_minor,
		                'line_total_minor', line.line_total_minor
		            )
		            ORDER BY line.line_no
		        ),
		        '[]'::jsonb
		    ) AS value
		    FROM shop_ch12.sales_order_item AS line
		    WHERE line.order_id = orders.order_id
		) AS items
		CROSS JOIN LATERAL (
		    SELECT COALESCE(
		        (
		            SELECT pg_catalog.jsonb_build_object(
		                'payment_id', paid.payment_id,
		                'state', paid.state,
		                'amount_minor', paid.amount_minor,
		                'created_at', paid.created_at
		            )
		            FROM shop_ch12.payment AS paid
		            WHERE paid.order_id = orders.order_id
		        ),
		        'null'::jsonb
		    ) AS value
		) AS payment
		WHERE orders.order_id = $1
		`,
		orderID,
	).Scan(
		&view.OrderID,
		&view.CustomerRef,
		&view.State,
		&view.TotalMinor,
		&view.CurrencyCode,
		&view.TraceID,
		&view.CreatedAt,
		&itemJSON,
		&paymentJSON,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return orderView{}, &apiError{
			HTTPStatus: 404,
			Code:       "order_not_found",
			Message:    "order does not exist",
			Retryable:  false,
		}
	}
	if err != nil {
		return orderView{}, mapDatabaseError(err)
	}
	if err := json.Unmarshal(itemJSON, &view.Items); err != nil {
		return orderView{}, &apiError{
			HTTPStatus: 500,
			Code:       "database_result_invalid",
			Message:    "order item result is invalid",
			Retryable:  false,
			Cause:      err,
		}
	}
	if string(paymentJSON) != "null" {
		var payment paymentView
		if err := json.Unmarshal(paymentJSON, &payment); err != nil {
			return orderView{}, &apiError{
				HTTPStatus: 500,
				Code:       "database_result_invalid",
				Message:    "payment result is invalid",
				Retryable:  false,
				Cause:      err,
			}
		}
		view.Payment = &payment
	}
	return view, nil
}

func (s *store) listOrders(
	ctx context.Context,
	after int64,
	limit int32,
) (orderPage, error) {
	connection, err := s.pool.Acquire(ctx)
	if err != nil {
		return orderPage{}, poolAcquireError(err)
	}
	defer connection.Release()

	rows, err := connection.Query(
		ctx,
		`
		WITH page AS (
		    SELECT
		        orders.order_id,
		        orders.state,
		        orders.total_minor,
		        orders.created_at
		    FROM shop_ch12.sales_order AS orders
		    WHERE orders.order_id > $1
		    ORDER BY orders.order_id
		    LIMIT $2
		),
		ranked AS (
		    SELECT
		        page.*,
		        pg_catalog.row_number() OVER (
		            ORDER BY page.order_id
		        ) AS page_position
		    FROM page
		)
		SELECT
		    ranked.order_id,
		    ranked.page_position,
		    ranked.state,
		    ranked.total_minor,
		    ranked.created_at,
		    items.value
		FROM ranked
		CROSS JOIN LATERAL (
		    SELECT COALESCE(
		        pg_catalog.jsonb_agg(
		            pg_catalog.jsonb_build_object(
		                'line_no', line.line_no,
		                'sku', line.sku,
		                'quantity', line.quantity,
		                'unit_price_minor', line.unit_price_minor,
		                'line_total_minor', line.line_total_minor
		            )
		            ORDER BY line.line_no
		        ),
		        '[]'::jsonb
		    ) AS value
		    FROM shop_ch12.sales_order_item AS line
		    WHERE line.order_id = ranked.order_id
		) AS items
		ORDER BY ranked.order_id
		`,
		after,
		limit+1,
	)
	if err != nil {
		return orderPage{}, mapDatabaseError(err)
	}
	defer rows.Close()

	page := orderPage{Items: make([]orderListItem, 0, limit)}
	for rows.Next() {
		var item orderListItem
		var itemJSON []byte
		if err := rows.Scan(
			&item.OrderID,
			&item.PagePosition,
			&item.State,
			&item.TotalMinor,
			&item.CreatedAt,
			&itemJSON,
		); err != nil {
			return orderPage{}, mapDatabaseError(err)
		}
		if err := json.Unmarshal(itemJSON, &item.Items); err != nil {
			return orderPage{}, &apiError{
				HTTPStatus: 500,
				Code:       "database_result_invalid",
				Message:    "order page result is invalid",
				Retryable:  false,
				Cause:      err,
			}
		}
		page.Items = append(page.Items, item)
	}
	if err := rows.Err(); err != nil {
		return orderPage{}, mapDatabaseError(err)
	}
	if len(page.Items) > int(limit) {
		page.Items = page.Items[:limit]
		cursor := page.Items[len(page.Items)-1].OrderID
		page.NextCursor = &cursor
	}
	return page, nil
}

func (s *store) readiness(
	ctx context.Context,
) (readyDetails, error) {
	connection, err := s.pool.Acquire(ctx)
	if err != nil {
		return readyDetails{}, poolAcquireError(err)
	}
	defer connection.Release()

	var details readyDetails
	err = connection.QueryRow(
		ctx,
		`
		SELECT
		    current_database(),
		    current_user,
		    NOT pg_catalog.pg_is_in_recovery(),
		    EXISTS (
		        SELECT 1
		        FROM shop_ch12.schema_version
		        WHERE singleton
		          AND version = 1
		          AND contract =
		              'pg36-ch12-service-contract-v1'
		    )
		`,
	).Scan(
		&details.Database,
		&details.User,
		&details.Writable,
		&details.SchemaReady,
	)
	if err != nil {
		return readyDetails{}, mapDatabaseError(err)
	}
	if details.Database != "pg36_shop" ||
		details.User != "pg36_app" ||
		!details.Writable ||
		!details.SchemaReady {
		return details, &apiError{
			HTTPStatus: 503,
			Code:       "database_contract_unready",
			Message:    "database identity or schema contract is not ready",
			Retryable:  true,
		}
	}
	details.Status = "ok"
	return details, nil
}

func (s *store) hold(
	ctx context.Context,
	duration time.Duration,
) error {
	connection, err := s.pool.Acquire(ctx)
	if err != nil {
		return poolAcquireError(err)
	}
	defer connection.Release()
	_, err = connection.Exec(
		ctx,
		`SELECT pg_catalog.pg_sleep($1::double precision)`,
		duration.Seconds(),
	)
	if ctx.Err() != nil {
		return mapDatabaseError(ctx.Err())
	}
	return mapDatabaseError(err)
}

func poolAcquireError(err error) error {
	return &apiError{
		HTTPStatus: 503,
		Code:       "pool_unavailable",
		Message:    "database connection pool acquisition failed",
		Retryable:  true,
		Cause:      err,
	}
}

func requireOneRow(
	commandTag pgconn.CommandTag,
	err error,
	operation string,
) error {
	if err != nil {
		return err
	}
	if commandTag.RowsAffected() != 1 {
		return &apiError{
			HTTPStatus: 500,
			Code:       "database_contract_drift",
			Message:    "database write cardinality violated the service contract",
			Retryable:  false,
			Cause: fmt.Errorf(
				"%s affected %d rows",
				operation,
				commandTag.RowsAffected(),
			),
		}
	}
	return nil
}

func isRetryableTransactionError(err error) bool {
	var databaseError *pgconn.PgError
	if !errors.As(err, &databaseError) {
		return false
	}
	return databaseError.Code == "40001" ||
		databaseError.Code == "40P01"
}

func mapDatabaseError(err error) error {
	if err == nil {
		return nil
	}
	var existing *apiError
	if errors.As(err, &existing) {
		return existing
	}
	if errors.Is(err, context.Canceled) {
		return &apiError{
			HTTPStatus: 499,
			Code:       "client_cancelled",
			Message:    "request was cancelled by the client",
			Retryable:  true,
			Cause:      err,
		}
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return &apiError{
			HTTPStatus: 504,
			Code:       "request_deadline",
			Message:    "request deadline expired",
			Retryable:  true,
			Cause:      err,
		}
	}

	var databaseError *pgconn.PgError
	if !errors.As(err, &databaseError) {
		return &apiError{
			HTTPStatus: 500,
			Code:       "database_error",
			Message:    "database operation failed",
			Retryable:  false,
			Cause:      err,
		}
	}

	switch databaseError.Code {
	case "40001", "40P01":
		return &apiError{
			HTTPStatus: 503,
			Code:       "transaction_retry_exhausted",
			Message:    "database transaction retry budget exhausted",
			Retryable:  true,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	case "57014":
		return &apiError{
			HTTPStatus: 504,
			Code:       "database_timeout",
			Message:    "database statement exceeded its time budget",
			Retryable:  true,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	case "23505":
		return &apiError{
			HTTPStatus: 409,
			Code:       "unique_conflict",
			Message:    "database uniqueness contract rejected the write",
			Retryable:  false,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	case "23503", "23514":
		return &apiError{
			HTTPStatus: 422,
			Code:       "database_constraint",
			Message:    "database constraint rejected the write",
			Retryable:  false,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	case "42501":
		return &apiError{
			HTTPStatus: 500,
			Code:       "database_privilege",
			Message:    "runtime role lacks a required privilege",
			Retryable:  false,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	default:
		return &apiError{
			HTTPStatus: 500,
			Code:       "database_error",
			Message:    "database operation failed",
			Retryable:  false,
			SQLState:   databaseError.Code,
			Cause:      err,
		}
	}
}
