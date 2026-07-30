#!/usr/bin/env python3
"""Exercise the ch12 service through HTTP and independent SQL evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LabError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LabError(message)


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict[str, str]
    body: Any


class ServiceLab:
    def __init__(
        self,
        base_url: str,
        service: str,
        evidence_dir: Path,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service = service
        self.evidence_dir = evidence_dir
        self.cases: list[dict[str, Any]] = []

    def psql(self, sql: str) -> str:
        connection = (
            f"service={self.service} "
            "application_name=pg36-ch12-observer"
        )
        command = [
            "psql",
            "-X",
            "-w",
            f"--dbname={connection}",
            "--set=ON_ERROR_STOP=1",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--command",
            sql,
        ]
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        if completed.returncode != 0:
            raise LabError(
                "observer SQL failed: "
                + completed.stderr.strip()
            )
        return completed.stdout.strip()

    def call(
        self,
        label: str,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 3.0,
        record: bool = True,
    ) -> HTTPResult:
        request_headers = dict(headers or {})
        body = raw_body
        if payload is not None:
            body = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(
                request,
                timeout=timeout,
            )
            status = response.status
            response_headers = {
                key.lower(): value
                for key, value in response.headers.items()
            }
            raw_response = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = {
                key.lower(): value
                for key, value in exc.headers.items()
            }
            raw_response = exc.read()

        content_type = response_headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                response_body: Any = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise LabError(
                    f"{label}: invalid JSON response"
                ) from exc
        else:
            response_body = raw_response.decode(
                "utf-8",
                errors="replace",
            )
        result = HTTPResult(
            status=status,
            headers=response_headers,
            body=response_body,
        )
        if record:
            self.cases.append(
                {
                    "label": label,
                    "status": status,
                    "replayed": response_headers.get(
                        "idempotency-replayed"
                    )
                    == "true",
                    "body": response_body,
                }
            )
        return result

    @staticmethod
    def error_code(result: HTTPResult) -> str:
        require(
            isinstance(result.body, dict)
            and isinstance(result.body.get("error"), dict),
            "expected an error envelope",
        )
        return str(result.body["error"].get("code"))

    def expect_error(
        self,
        result: HTTPResult,
        status: int,
        code: str,
    ) -> None:
        require(
            result.status == status,
            f"expected HTTP {status}, got {result.status}",
        )
        require(
            self.error_code(result) == code,
            f"expected error {code}, got {self.error_code(result)}",
        )

    def state_snapshot(self) -> dict[str, Any]:
        raw = self.psql(
            """
            SELECT pg_catalog.jsonb_build_object(
                'orders',
                    (SELECT count(*)
                     FROM shop_ch12.sales_order),
                'items',
                    (SELECT count(*)
                     FROM shop_ch12.sales_order_item),
                'payments',
                    (SELECT count(*)
                     FROM shop_ch12.payment),
                'outbox',
                    (SELECT count(*)
                     FROM shop_ch12.outbox),
                'order_requests',
                    (SELECT count(*)
                     FROM shop_ch12.order_request),
                'payment_requests',
                    (SELECT count(*)
                     FROM shop_ch12.payment_request),
                'inventory',
                    (SELECT pg_catalog.jsonb_object_agg(
                                sku,
                                pg_catalog.jsonb_build_object(
                                    'available', available,
                                    'version', version
                                )
                                ORDER BY sku
                            )
                     FROM shop_ch12.inventory)
            );
            """
        )
        return json.loads(raw)

    def active_sleepers(self) -> int:
        return int(
            self.psql(
                """
                SELECT count(*)
                FROM pg_catalog.pg_stat_activity
                WHERE datname = current_database()
                  AND application_name = 'pg36-ch12-api'
                  AND state = 'active'
                  AND query LIKE
                      'SELECT pg_catalog.pg_sleep%';
                """
            )
        )

    def wait_for_sleepers(
        self,
        target: int,
        timeout: float,
    ) -> int:
        deadline = time.monotonic() + timeout
        last = -1
        while time.monotonic() < deadline:
            last = self.active_sleepers()
            if last == target:
                return last
            time.sleep(0.02)
        raise LabError(
            f"sleeping workers did not reach {target}; last={last}"
        )

    def run_business_flow(self) -> None:
        live = self.call(
            "liveness",
            "GET",
            "/health/live",
            headers={"X-Request-ID": "trace-live-001"},
        )
        require(
            live.status == 200
            and live.body == {"status": "ok"},
            "liveness contract drifted",
        )

        ready = self.call(
            "readiness",
            "GET",
            "/health/ready",
            headers={"X-Request-ID": "trace-ready-001"},
        )
        require(
            ready.status == 200
            and ready.body
            == {
                "status": "ok",
                "database": "pg36_shop",
                "user": "pg36_app",
                "writable": True,
                "schema_ready": True,
            },
            "readiness identity contract drifted",
        )

        order_payload = {
            "request_key": "order-001",
            "customer_ref": "customer-001",
            "sku": "PG36-SKU-001",
            "quantity": 2,
        }
        expected_order = {
            "order_id": 1200001,
            "state": "placed",
            "total_minor": 25800,
            "currency_code": "CNY",
        }
        order = self.call(
            "order-created",
            "POST",
            "/v1/orders",
            payload=order_payload,
            headers={"X-Request-ID": "trace-order-001"},
        )
        require(
            order.status == 201
            and order.body == expected_order,
            "order response drifted",
        )

        replay = self.call(
            "order-replayed",
            "POST",
            "/v1/orders",
            payload=order_payload,
            headers={"X-Request-ID": "trace-order-replay"},
        )
        require(
            replay.status == 201
            and replay.body == expected_order
            and replay.headers.get("idempotency-replayed")
            == "true",
            "order replay drifted",
        )

        conflict_payload = dict(order_payload)
        conflict_payload["quantity"] = 3
        self.expect_error(
            self.call(
                "order-idempotency-conflict",
                "POST",
                "/v1/orders",
                payload=conflict_payload,
                headers={
                    "X-Request-ID": "trace-order-conflict"
                },
            ),
            409,
            "idempotency_conflict",
        )

        self.expect_error(
            self.call(
                "order-insufficient",
                "POST",
                "/v1/orders",
                payload={
                    "request_key": "order-insufficient",
                    "customer_ref": "customer-003",
                    "sku": "PG36-SKU-001",
                    "quantity": 999,
                },
                headers={
                    "X-Request-ID": "trace-order-insufficient"
                },
            ),
            409,
            "insufficient_inventory",
        )

        self.expect_error(
            self.call(
                "order-missing-sku",
                "POST",
                "/v1/orders",
                payload={
                    "request_key": "order-missing",
                    "customer_ref": "customer-003",
                    "sku": "PG36-NOT-FOUND",
                    "quantity": 1,
                },
                headers={
                    "X-Request-ID": "trace-order-missing"
                },
            ),
            404,
            "sku_not_found",
        )

        self.expect_error(
            self.call(
                "order-invalid-json-shape",
                "POST",
                "/v1/orders",
                raw_body=(
                    b'{"request_key":"bad","unexpected":true}'
                ),
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": "trace-invalid-json",
                },
            ),
            400,
            "invalid_json",
        )

        before_timeout = self.state_snapshot()
        self.expect_error(
            self.call(
                "order-statement-timeout",
                "POST",
                "/v1/orders",
                payload={
                    "request_key": "order-timeout",
                    "customer_ref": "customer-003",
                    "sku": "PG36-SKU-002",
                    "quantity": 1,
                },
                headers={
                    "X-Request-ID": "trace-timeout-001",
                    "X-PG36-Fault": "statement-timeout",
                },
            ),
            504,
            "database_timeout",
        )
        require(
            self.state_snapshot() == before_timeout,
            "statement timeout changed committed business state",
        )

        retry_order = self.call(
            "order-serialization-retry",
            "POST",
            "/v1/orders",
            payload={
                "request_key": "order-retry",
                "customer_ref": "customer-002",
                "sku": "PG36-SKU-002",
                "quantity": 1,
            },
            headers={
                "X-Request-ID": "trace-retry-001",
                "X-PG36-Fault": "retry-once",
            },
        )
        require(
            retry_order.status == 201
            and retry_order.body
            == {
                "order_id": 1200002,
                "state": "placed",
                "total_minor": 8900,
                "currency_code": "CNY",
            },
            "serialization retry did not commit exactly once",
        )

        first_page = self.call(
            "order-page-first",
            "GET",
            "/v1/orders?limit=1",
            headers={"X-Request-ID": "trace-page-001"},
        )
        require(
            first_page.status == 200
            and len(first_page.body["items"]) == 1
            and first_page.body["items"][0]["order_id"]
            == 1200001
            and first_page.body["items"][0]["page_position"]
            == 1
            and first_page.body["next_cursor"] == 1200001,
            "first keyset page drifted",
        )
        second_page = self.call(
            "order-page-second",
            "GET",
            "/v1/orders?limit=1&after=1200001",
            headers={"X-Request-ID": "trace-page-002"},
        )
        require(
            second_page.status == 200
            and len(second_page.body["items"]) == 1
            and second_page.body["items"][0]["order_id"]
            == 1200002
            and second_page.body["next_cursor"] is None,
            "second keyset page drifted",
        )

        payment_payload = {
            "idempotency_key": "pay-001",
            "order_id": 1200001,
            "amount_minor": 25800,
        }
        self.expect_error(
            self.call(
                "payment-amount-mismatch",
                "POST",
                "/v1/payments",
                payload={
                    "idempotency_key": "pay-wrong",
                    "order_id": 1200001,
                    "amount_minor": 1,
                },
                headers={
                    "X-Request-ID": "trace-payment-wrong"
                },
            ),
            422,
            "amount_mismatch",
        )

        expected_payment = {
            "payment_id": 1200001,
            "order_id": 1200001,
            "state": "captured",
            "amount_minor": 25800,
            "currency_code": "CNY",
        }
        payment = self.call(
            "payment-captured",
            "POST",
            "/v1/payments",
            payload=payment_payload,
            headers={"X-Request-ID": "trace-payment-001"},
        )
        require(
            payment.status == 201
            and payment.body == expected_payment,
            "payment response drifted",
        )

        payment_replay = self.call(
            "payment-replayed",
            "POST",
            "/v1/payments",
            payload=payment_payload,
            headers={
                "X-Request-ID": "trace-payment-replay"
            },
        )
        require(
            payment_replay.status == 201
            and payment_replay.body == expected_payment
            and payment_replay.headers.get(
                "idempotency-replayed"
            )
            == "true",
            "payment replay drifted",
        )

        mismatch_payment = dict(payment_payload)
        mismatch_payment["amount_minor"] = 25801
        self.expect_error(
            self.call(
                "payment-idempotency-conflict",
                "POST",
                "/v1/payments",
                payload=mismatch_payment,
                headers={
                    "X-Request-ID":
                        "trace-payment-conflict"
                },
            ),
            409,
            "idempotency_conflict",
        )

        self.expect_error(
            self.call(
                "payment-already-paid",
                "POST",
                "/v1/payments",
                payload={
                    "idempotency_key": "pay-002",
                    "order_id": 1200001,
                    "amount_minor": 25800,
                },
                headers={
                    "X-Request-ID":
                        "trace-payment-already-paid"
                },
            ),
            409,
            "already_paid",
        )

        order_view = self.call(
            "order-read",
            "GET",
            "/v1/orders/1200001",
            headers={"X-Request-ID": "trace-order-read"},
        )
        require(
            order_view.status == 200
            and order_view.body["state"] == "paid"
            and order_view.body["trace_id"]
            == "trace-order-001"
            and order_view.body["items"]
            == [
                {
                    "line_no": 1,
                    "sku": "PG36-SKU-001",
                    "quantity": 2,
                    "unit_price_minor": 12900,
                    "line_total_minor": 25800,
                }
            ]
            and order_view.body["payment"]["payment_id"]
            == 1200001,
            "order LATERAL read model drifted",
        )

        self.expect_error(
            self.call(
                "order-not-found",
                "GET",
                "/v1/orders/9999999",
                headers={
                    "X-Request-ID": "trace-order-not-found"
                },
            ),
            404,
            "order_not_found",
        )

        self.expect_error(
            self.call(
                "order-injection-shaped-input",
                "POST",
                "/v1/orders",
                payload={
                    "request_key": "order-injection",
                    "customer_ref": "customer-004",
                    "sku": "PG36-SKU-001' OR true--",
                    "quantity": 1,
                },
                headers={
                    "X-Request-ID": "trace-injection"
                },
            ),
            400,
            "invalid_order",
        )

    def run_client_cancel(self) -> None:
        outcome: dict[str, str] = {}

        def cancelled_request() -> None:
            try:
                self.call(
                    "client-cancel-internal",
                    "GET",
                    "/debug/hold?ms=2000",
                    headers={
                        "X-Request-ID": "trace-client-cancel"
                    },
                    timeout=0.4,
                    record=False,
                )
                outcome["result"] = "unexpected-response"
            except Exception as exc:  # expected transport timeout
                outcome["result"] = type(exc).__name__

        worker = threading.Thread(
            target=cancelled_request,
            name="client-cancel",
        )
        worker.start()
        observed = self.wait_for_sleepers(1, 1.0)
        worker.join(timeout=2.0)
        require(not worker.is_alive(), "cancel client did not return")

        deadline = time.monotonic() + 1.5
        cleared = self.active_sleepers()
        while cleared != 0 and time.monotonic() < deadline:
            time.sleep(0.02)
            cleared = self.active_sleepers()
        require(
            outcome.get("result") != "unexpected-response",
            "client cancellation unexpectedly received a response",
        )
        require(
            observed == 1 and cleared == 0,
            "cancelled PostgreSQL worker did not clear",
        )
        document = {
            "schema": "pg36-ch12-client-cancel-v1",
            "transport_result": outcome.get("result"),
            "active_workers_observed": observed,
            "active_workers_after_cancel": cleared,
        }
        (
            self.evidence_dir / "client-cancel.json"
        ).write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def run_pool_saturation(self) -> None:
        holder_results: list[HTTPResult | Exception | None] = [
            None,
            None,
        ]

        def hold(index: int) -> None:
            try:
                holder_results[index] = self.call(
                    f"pool-holder-{index + 1}",
                    "GET",
                    "/debug/hold?ms=1000",
                    headers={
                        "X-Request-ID":
                            f"trace-pool-holder-{index + 1}"
                    },
                    timeout=3.0,
                    record=False,
                )
            except Exception as exc:
                holder_results[index] = exc

        holders = [
            threading.Thread(
                target=hold,
                args=(index,),
                name=f"pool-holder-{index + 1}",
            )
            for index in range(2)
        ]
        for holder in holders:
            holder.start()
        observed = self.wait_for_sleepers(2, 1.0)

        live = self.call(
            "pool-saturated-liveness",
            "GET",
            "/health/live",
            headers={
                "X-Request-ID": "trace-pool-live"
            },
        )
        ready = self.call(
            "pool-saturated-readiness",
            "GET",
            "/health/ready",
            headers={
                "X-Request-ID": "trace-pool-ready"
            },
        )
        request = self.call(
            "pool-saturated-request",
            "GET",
            "/v1/orders/1200001",
            headers={
                "X-Request-ID": "trace-pool-request",
                "X-PG36-Deadline-Ms": "100",
            },
        )

        for holder in holders:
            holder.join(timeout=3.0)
        require(
            all(not holder.is_alive() for holder in holders),
            "pool holders did not complete",
        )
        holder_statuses = [
            value.status
            if isinstance(value, HTTPResult)
            else -1
            for value in holder_results
        ]
        require(
            observed == 2,
            "pool did not reach MaxConns=2",
        )
        require(
            live.status == 200,
            "liveness depended on the database pool",
        )
        self.expect_error(ready, 503, "pool_unavailable")
        self.expect_error(request, 503, "pool_unavailable")
        require(
            holder_statuses == [200, 200],
            f"pool holders drifted: {holder_statuses}",
        )

        recovered = self.call(
            "pool-recovered-readiness",
            "GET",
            "/health/ready",
            headers={
                "X-Request-ID": "trace-pool-recovered"
            },
        )
        require(
            recovered.status == 200,
            "readiness did not recover after pool release",
        )

        document = {
            "schema": "pg36-ch12-pool-saturation-v1",
            "max_conns": 2,
            "database_workers_observed": observed,
            "liveness_status": live.status,
            "readiness_status": ready.status,
            "readiness_error": self.error_code(ready),
            "business_request_status": request.status,
            "business_request_error": self.error_code(request),
            "holder_statuses": holder_statuses,
            "recovered_readiness_status": recovered.status,
        }
        (
            self.evidence_dir / "pool-saturation.json"
        ).write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_trace_evidence(self) -> None:
        raw = self.psql(
            """
            SELECT pg_catalog.jsonb_build_object(
                'order_trace',
                    (SELECT trace_id
                     FROM shop_ch12.sales_order
                     WHERE order_id = 1200001),
                'payment_trace',
                    (SELECT trace_id
                     FROM shop_ch12.payment
                     WHERE payment_id = 1200001),
                'outbox_traces',
                    (SELECT pg_catalog.jsonb_object_agg(
                                event_key,
                                trace_id
                                ORDER BY event_key
                            )
                     FROM shop_ch12.outbox),
                'application_names',
                    (SELECT pg_catalog.jsonb_agg(
                                DISTINCT application_name
                            )
                     FROM pg_catalog.pg_stat_activity
                     WHERE datname = current_database()
                       AND application_name =
                           'pg36-ch12-api')
            );
            """
        )
        document = json.loads(raw)
        require(
            document["order_trace"] == "trace-order-001"
            and document["payment_trace"]
            == "trace-payment-001"
            and document["outbox_traces"]
            == {
                "order:order-001:placed":
                    "trace-order-001",
                "order:order-retry:placed":
                    "trace-retry-001",
                "payment:pay-001:captured":
                    "trace-payment-001",
            }
            and document["application_names"]
            == ["pg36-ch12-api"],
            "trace correlation relationship drifted",
        )
        document["schema"] = "pg36-ch12-trace-correlation-v1"
        (
            self.evidence_dir / "trace-correlation.json"
        ).write_text(
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_final_evidence(self) -> None:
        final_state = self.state_snapshot()
        require(
            final_state
            == {
                "orders": 2,
                "items": 2,
                "payments": 1,
                "outbox": 3,
                "order_requests": 2,
                "payment_requests": 1,
                "inventory": {
                    "PG36-SKU-001": {
                        "available": 8,
                        "version": 1,
                    },
                    "PG36-SKU-002": {
                        "available": 4,
                        "version": 1,
                    },
                },
            },
            f"final database state drifted: {final_state}",
        )
        final_state["schema"] = "pg36-ch12-final-state-v1"
        (
            self.evidence_dir / "db-final.json"
        ).write_text(
            json.dumps(
                final_state,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        metrics = self.call(
            "metrics-snapshot",
            "GET",
            "/metrics",
            headers={"X-Request-ID": "trace-metrics-001"},
            record=False,
        )
        require(
            metrics.status == 200
            and isinstance(metrics.body, str),
            "metrics endpoint drifted",
        )
        metric_text = metrics.body
        for pattern in [
            r"pg36_transaction_retries_total 1(?:\.0+)?$",
            r"pg36_idempotent_replays_total 2(?:\.0+)?$",
            r'pg36_db_errors_total\{sqlstate="40001"\} 1$',
            r'pg36_db_errors_total\{sqlstate="57014"\} 1$',
            r"pg36_pool_canceled_acquire_total [2-9][0-9]*$",
            r'pg36_pool_connections\{state="max"\} 2$',
        ]:
            require(
                re.search(pattern, metric_text, re.MULTILINE)
                is not None,
                f"missing metric relationship: {pattern}",
            )
        (self.evidence_dir / "metrics.txt").write_text(
            metric_text,
            encoding="utf-8",
        )

        api_document = {
            "schema": "pg36-ch12-api-results-v1",
            "status": "ok",
            "cases": self.cases,
        }
        (self.evidence_dir / "api-results.json").write_text(
            json.dumps(
                api_document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def run(self) -> None:
        self.run_business_flow()
        self.write_trace_evidence()
        self.run_client_cancel()
        self.run_pool_saturation()
        self.write_final_evidence()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        lab = ServiceLab(
            base_url=args.base_url,
            service=args.service,
            evidence_dir=args.evidence_dir,
        )
        lab.run()
    except (
        LabError,
        OSError,
        subprocess.SubprocessError,
        urllib.error.URLError,
    ) as exc:
        print(f"ch12 service lab failed: {exc}", file=sys.stderr)
        return 1

    print("status=ok")
    print("business=orders:2/payments:1/outbox:3")
    print("idempotency=order+payment/replays:2/conflicts:2")
    print("failure=57014:rollback/40001:retry-once/client-cancel:cleared")
    print("pool=max:2/live:200/ready:503/request:503/recovered:200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
