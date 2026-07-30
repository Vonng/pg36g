package main

import (
	"encoding/json"
	"fmt"
	"time"
)

type createOrderRequest struct {
	RequestKey  string `json:"request_key"`
	CustomerRef string `json:"customer_ref"`
	SKU         string `json:"sku"`
	Quantity    int32  `json:"quantity"`
}

type orderResponse struct {
	OrderID      int64  `json:"order_id"`
	State        string `json:"state"`
	TotalMinor   int64  `json:"total_minor"`
	CurrencyCode string `json:"currency_code"`
}

type capturePaymentRequest struct {
	IdempotencyKey string `json:"idempotency_key"`
	OrderID        int64  `json:"order_id"`
	AmountMinor    int64  `json:"amount_minor"`
}

type paymentResponse struct {
	PaymentID   int64  `json:"payment_id"`
	OrderID     int64  `json:"order_id"`
	State       string `json:"state"`
	AmountMinor int64  `json:"amount_minor"`
	Currency    string `json:"currency_code"`
}

type orderItemView struct {
	LineNo         int16  `json:"line_no"`
	SKU            string `json:"sku"`
	Quantity       int32  `json:"quantity"`
	UnitPriceMinor int64  `json:"unit_price_minor"`
	LineTotalMinor int64  `json:"line_total_minor"`
}

type paymentView struct {
	PaymentID   int64     `json:"payment_id"`
	State       string    `json:"state"`
	AmountMinor int64     `json:"amount_minor"`
	CreatedAt   time.Time `json:"created_at"`
}

type orderView struct {
	OrderID      int64           `json:"order_id"`
	CustomerRef  string          `json:"customer_ref"`
	State        string          `json:"state"`
	TotalMinor   int64           `json:"total_minor"`
	CurrencyCode string          `json:"currency_code"`
	TraceID      string          `json:"trace_id"`
	CreatedAt    time.Time       `json:"created_at"`
	Items        []orderItemView `json:"items"`
	Payment      *paymentView    `json:"payment"`
}

type orderListItem struct {
	OrderID      int64           `json:"order_id"`
	PagePosition int64           `json:"page_position"`
	State        string          `json:"state"`
	TotalMinor   int64           `json:"total_minor"`
	CreatedAt    time.Time       `json:"created_at"`
	Items        []orderItemView `json:"items"`
}

type orderPage struct {
	Items      []orderListItem `json:"items"`
	NextCursor *int64          `json:"next_cursor"`
}

type readyDetails struct {
	Status      string `json:"status"`
	Database    string `json:"database"`
	User        string `json:"user"`
	Writable    bool   `json:"writable"`
	SchemaReady bool   `json:"schema_ready"`
}

type apiError struct {
	HTTPStatus int
	Code       string
	Message    string
	Retryable  bool
	SQLState   string
	Cause      error
}

func (e *apiError) Error() string {
	if e.Cause == nil {
		return e.Code
	}
	return fmt.Sprintf("%s: %v", e.Code, e.Cause)
}

func (e *apiError) Unwrap() error {
	return e.Cause
}

type errorEnvelope struct {
	Error errorBody `json:"error"`
}

type errorBody struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
	TraceID   string `json:"trace_id"`
}

func decodeJSONBytes[T any](raw []byte) (T, error) {
	var value T
	if err := json.Unmarshal(raw, &value); err != nil {
		return value, err
	}
	return value, nil
}
