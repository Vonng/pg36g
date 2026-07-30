# PG36 ch12 frozen reference service

This directory is an independent Go module for the chapter 12 executable
contract. It is intentionally small and framework-free:

- `main.go`: configuration, lifecycle, and graceful shutdown;
- `server.go`: HTTP routes, health, structured errors, and JSON logs;
- `store.go`: pgxpool configuration, parameterized SQL, transactions, retry,
  idempotency, and read models;
- `model.go`: bounded API and error types;
- `metrics.go`: request, SQLSTATE, retry, replay, and pgxpool metrics.

Frozen validation combination:

```text
Go module requires Go 1.25+
github.com/jackc/pgx/v5 v5.10.0
DefaultQueryExecMode=QueryExecModeExec
application_name=pg36-ch12-api
```

Build:

```bash
GOWORK=off go test ./...
GOWORK=off go vet ./...
GOWORK=off go build -trimpath .
```

Runtime configuration:

```text
PG36_DATABASE_URL   required; never logged
PG36_HTTP_ADDR      default 127.0.0.1:18012
PG36_MAX_CONNS      default 8
PG36_MIN_IDLE_CONNS default 1
PG36_ENABLE_FAULTS  lab only; omit in normal deployments
```

Use `../task.sh all` for the deterministic database, HTTP, failure, reset, and
review workflow. Do not run the fixture actions against an unconfirmed
production target.
