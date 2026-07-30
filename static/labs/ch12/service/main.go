package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(
			os.Stdout,
			&slog.HandlerOptions{Level: slog.LevelInfo},
		),
	)

	databaseURL := os.Getenv("PG36_DATABASE_URL")
	if databaseURL == "" {
		logger.Error(
			"configuration",
			"error", "PG36_DATABASE_URL is required",
		)
		os.Exit(64)
	}
	listenAddress := environment(
		"PG36_HTTP_ADDR",
		"127.0.0.1:18012",
	)
	maxConns := int32(environmentInteger("PG36_MAX_CONNS", 8))
	minIdleConns := int32(
		environmentInteger("PG36_MIN_IDLE_CONNS", 1),
	)
	if maxConns < 1 ||
		maxConns > 256 ||
		minIdleConns < 0 ||
		minIdleConns > maxConns {
		logger.Error(
			"configuration",
			"error", "invalid connection pool bounds",
		)
		os.Exit(64)
	}

	startupContext, cancelStartup := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancelStartup()
	metrics := newServiceMetrics()
	database, err := newStore(
		startupContext,
		databaseURL,
		maxConns,
		minIdleConns,
		metrics,
	)
	if err != nil {
		logger.Error("database_startup", "error", err)
		os.Exit(1)
	}
	defer database.pool.Close()

	api := &apiServer{
		store:         database,
		metrics:       metrics,
		logger:        logger,
		faultsEnabled: os.Getenv("PG36_ENABLE_FAULTS") == "1",
	}
	server := &http.Server{
		Addr:              listenAddress,
		Handler:           api.handler(),
		ReadHeaderTimeout: 2 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	serverErrors := make(chan error, 1)
	go func() {
		logger.Info(
			"service_start",
			"address", listenAddress,
			"max_conns", maxConns,
			"min_idle_conns", minIdleConns,
			"query_mode", "exec",
			"faults_enabled", api.faultsEnabled,
		)
		serverErrors <- server.ListenAndServe()
	}()

	signalContext, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()

	select {
	case <-signalContext.Done():
		logger.Info("service_stop", "reason", "signal")
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			logger.Error("http_server", "error", err)
			os.Exit(1)
		}
	}

	shutdownContext, cancelShutdown := context.WithTimeout(
		context.Background(),
		3*time.Second,
	)
	defer cancelShutdown()
	if err := server.Shutdown(shutdownContext); err != nil {
		logger.Error("service_shutdown", "error", err)
		os.Exit(1)
	}
	logger.Info("service_stopped")
}

func environment(name string, fallback string) string {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	return value
}

func environmentInteger(name string, fallback int) int {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return -1
	}
	return value
}
