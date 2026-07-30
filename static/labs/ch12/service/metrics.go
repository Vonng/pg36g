package main

import (
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type routeMetric struct {
	Count       uint64
	DurationSum float64
}

type serviceMetrics struct {
	mu sync.Mutex

	routes map[string]routeMetric
	errors map[string]uint64

	transactionRetries atomic.Uint64
	idempotentReplays  atomic.Uint64
}

func newServiceMetrics() *serviceMetrics {
	return &serviceMetrics{
		routes: make(map[string]routeMetric),
		errors: make(map[string]uint64),
	}
}

func (m *serviceMetrics) observeRequest(
	route string,
	status int,
	duration time.Duration,
) {
	key := fmt.Sprintf("%s|%dxx", route, status/100)
	m.mu.Lock()
	current := m.routes[key]
	current.Count++
	current.DurationSum += duration.Seconds()
	m.routes[key] = current
	m.mu.Unlock()
}

func (m *serviceMetrics) observeDBError(sqlState string) {
	if sqlState == "" {
		sqlState = "none"
	}
	m.mu.Lock()
	m.errors[sqlState]++
	m.mu.Unlock()
}

func (m *serviceMetrics) render(
	writer io.Writer,
	pool *pgxpool.Pool,
) {
	stat := pool.Stat()

	m.mu.Lock()
	routeKeys := make([]string, 0, len(m.routes))
	for key := range m.routes {
		routeKeys = append(routeKeys, key)
	}
	sort.Strings(routeKeys)
	errorKeys := make([]string, 0, len(m.errors))
	for key := range m.errors {
		errorKeys = append(errorKeys, key)
	}
	sort.Strings(errorKeys)
	routes := make(map[string]routeMetric, len(m.routes))
	for key, value := range m.routes {
		routes[key] = value
	}
	errorsByState := make(map[string]uint64, len(m.errors))
	for key, value := range m.errors {
		errorsByState[key] = value
	}
	m.mu.Unlock()

	fmt.Fprintln(writer, "# TYPE pg36_http_requests_total counter")
	for _, key := range routeKeys {
		parts := strings.SplitN(key, "|", 2)
		fmt.Fprintf(
			writer,
			"pg36_http_requests_total{route=%q,code_class=%q} %d\n",
			parts[0],
			parts[1],
			routes[key].Count,
		)
	}
	fmt.Fprintln(
		writer,
		"# TYPE pg36_http_request_duration_seconds_sum counter",
	)
	for _, key := range routeKeys {
		parts := strings.SplitN(key, "|", 2)
		fmt.Fprintf(
			writer,
			"pg36_http_request_duration_seconds_sum{route=%q,code_class=%q} %.6f\n",
			parts[0],
			parts[1],
			routes[key].DurationSum,
		)
	}
	fmt.Fprintln(writer, "# TYPE pg36_db_errors_total counter")
	for _, sqlState := range errorKeys {
		fmt.Fprintf(
			writer,
			"pg36_db_errors_total{sqlstate=%q} %d\n",
			sqlState,
			errorsByState[sqlState],
		)
	}
	fmt.Fprintln(
		writer,
		"# TYPE pg36_transaction_retries_total counter",
	)
	fmt.Fprintf(
		writer,
		"pg36_transaction_retries_total %d\n",
		m.transactionRetries.Load(),
	)
	fmt.Fprintln(
		writer,
		"# TYPE pg36_idempotent_replays_total counter",
	)
	fmt.Fprintf(
		writer,
		"pg36_idempotent_replays_total %d\n",
		m.idempotentReplays.Load(),
	)

	fmt.Fprintln(writer, "# TYPE pg36_pool_acquire_total counter")
	fmt.Fprintf(
		writer,
		"pg36_pool_acquire_total %d\n",
		stat.AcquireCount(),
	)
	fmt.Fprintln(
		writer,
		"# TYPE pg36_pool_acquire_seconds_total counter",
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_acquire_seconds_total %.6f\n",
		stat.AcquireDuration().Seconds(),
	)
	fmt.Fprintln(
		writer,
		"# TYPE pg36_pool_empty_acquire_total counter",
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_empty_acquire_total %d\n",
		stat.EmptyAcquireCount(),
	)
	fmt.Fprintln(
		writer,
		"# TYPE pg36_pool_canceled_acquire_total counter",
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_canceled_acquire_total %d\n",
		stat.CanceledAcquireCount(),
	)
	fmt.Fprintln(writer, "# TYPE pg36_pool_connections gauge")
	fmt.Fprintf(
		writer,
		"pg36_pool_connections{state=\"acquired\"} %d\n",
		stat.AcquiredConns(),
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_connections{state=\"idle\"} %d\n",
		stat.IdleConns(),
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_connections{state=\"total\"} %d\n",
		stat.TotalConns(),
	)
	fmt.Fprintf(
		writer,
		"pg36_pool_connections{state=\"max\"} %d\n",
		stat.MaxConns(),
	)
}
