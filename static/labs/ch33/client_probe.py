#!/usr/bin/env python3
"""Continuously write idempotent tokens through the Pigsty service path."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg


INSERT = """
INSERT INTO pg36_ch33.write_probe (
    run_id, attempt_no, token, client_sent_at
)
VALUES (%s, %s, %s, %s)
RETURNING
    committed_at,
    pg_current_wal_insert_lsn()::text,
    (pg_control_checkpoint()).timeline_id,
    inet_server_addr()::text,
    pg_backend_pid(),
    pg_is_in_recovery()
"""


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def append_json(stream: Any, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def close_connection(connection: psycopg.Connection[Any] | None) -> None:
    if connection is None:
        return
    try:
        connection.close()
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0 or args.interval <= 0:
        print("duration and interval must be positive", file=sys.stderr)
        return 64
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.parent.chmod(0o700)
    started = time.monotonic()
    deadline = started + args.duration
    attempts = 0
    acknowledged = 0
    unknown = 0
    connection: psycopg.Connection[Any] | None = None
    with args.output.open("x", encoding="utf-8") as stream:
        args.output.chmod(0o600)
        while time.monotonic() < deadline:
            attempts += 1
            attempt_started_ns = time.monotonic_ns()
            sent_at = utc_now()
            token = f"{args.run_id}:{attempts:08d}"
            record: dict[str, Any] = {
                "schema": "pg36-ch33-client-event-v1",
                "run_id": args.run_id,
                "attempt_no": attempts,
                "token": token,
                "client_sent_at": sent_at,
                "attempt_started_monotonic_ns": attempt_started_ns,
            }
            try:
                if connection is None or connection.closed:
                    connection = psycopg.connect(
                        "service=pg36-ch33",
                        autocommit=True,
                    )
                with connection.cursor() as cursor:
                    cursor.execute(
                        INSERT,
                        (args.run_id, attempts, token, sent_at),
                    )
                    row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("INSERT returned no identity")
                acknowledged += 1
                record.update(
                    {
                        "outcome": "acknowledged",
                        "committed_at": row[0].isoformat(),
                        "wal_lsn": str(row[1]),
                        "timeline": int(row[2]),
                        "server_address": (
                            None if row[3] is None else str(row[3])
                        ),
                        "backend_pid": int(row[4]),
                        "in_recovery": bool(row[5]),
                    }
                )
                if acknowledged == 1:
                    args.ready_file.write_text(
                        json.dumps(
                            {
                                "status": "ready",
                                "run_id": args.run_id,
                                "first_ack_attempt": attempts,
                            },
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    args.ready_file.chmod(0o600)
            except Exception as exc:
                unknown += 1
                record.update(
                    {
                        "outcome": "unknown",
                        "error_class": type(exc).__name__,
                        "sqlstate": getattr(exc, "sqlstate", None),
                    }
                )
                close_connection(connection)
                connection = None
            record["attempt_finished_monotonic_ns"] = time.monotonic_ns()
            append_json(stream, record)
            due = started + attempts * args.interval
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        append_json(
            stream,
            {
                "schema": "pg36-ch33-client-summary-v1",
                "run_id": args.run_id,
                "outcome": "summary",
                "attempts": attempts,
                "acknowledged": acknowledged,
                "unknown": unknown,
                "finished_at": utc_now(),
                "finished_monotonic_ns": time.monotonic_ns(),
            },
        )
    close_connection(connection)
    if acknowledged == 0:
        print("client probe produced no acknowledged write", file=sys.stderr)
        return 1
    print(f"attempts={attempts}")
    print(f"acknowledged={acknowledged}")
    print(f"unknown={unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
