#!/usr/bin/env python3
"""Prove that a fast ADD COLUMN can still lose its lock budget."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import selectors
import subprocess
import sys
import time
from pathlib import Path


class LockCaseError(RuntimeError):
    pass


def psql_base(service: str, application_name: str) -> list[str]:
    return [
        "psql",
        "-X",
        "-w",
        "-qA",
        f"--dbname=service={service} application_name={application_name}",
        "--set=ON_ERROR_STOP=1",
    ]


def run_psql(
    service: str,
    application_name: str,
    sql: str,
    *,
    csv_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = psql_base(service, application_name)
    if csv_output:
        command.append("--csv")
    else:
        command.append("--tuples-only")
    command.extend(["--command", sql])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PSQLRC": os.devnull},
    )


def wait_for_marker(
    process: subprocess.Popen[str],
    marker: str,
    timeout: float,
) -> list[str]:
    if process.stdout is None:
        raise LockCaseError("holder stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    lines: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LockCaseError(
                f"holder exited before {marker}: {process.returncode}"
            )
        events = selector.select(max(0.0, deadline - time.monotonic()))
        if not events:
            continue
        line = process.stdout.readline()
        if not line:
            continue
        lines.append(line)
        if marker in line:
            return lines
    raise LockCaseError(f"timed out waiting for {marker}")


def parse_csv_rows(document: str) -> list[dict[str, str]]:
    if not document.strip():
        return []
    return list(csv.DictReader(io.StringIO(document)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default="pg36-admin")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument(
        "--script-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()

    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    holder: subprocess.Popen[str] | None = None
    holder_lines: list[str] = []

    try:
        holder = subprocess.Popen(
            psql_base(args.service, "pg36-ch11-lock-holder"),
            cwd=args.script_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "PSQLRC": os.devnull},
        )
        if holder.stdin is None:
            raise LockCaseError("holder stdin is unavailable")
        holder.stdin.write(
            "\\set ON_ERROR_STOP on\n"
            "\\ir context.sql\n"
            "BEGIN;\n"
            "SET LOCAL statement_timeout = '20s';\n"
            "LOCK TABLE shop_private.ch11_order "
            "IN ACCESS SHARE MODE;\n"
            "\\echo CH11_HOLDER_READY\n"
        )
        holder.stdin.flush()
        holder_lines.extend(
            wait_for_marker(holder, "CH11_HOLDER_READY", 10.0)
        )

        waiter_command = psql_base(
            args.service,
            "pg36-ch11-lock-waiter",
        )
        waiter_command.extend(
            [
                "--set=VERBOSITY=verbose",
                f"--file={args.script_dir / 'lock-attempt.sql'}",
            ]
        )
        waiter = subprocess.Popen(
            waiter_command,
            cwd=args.script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PSQLRC": os.devnull},
        )

        graph_rows: list[dict[str, str]] = []
        graph_document = ""
        graph_sql = """
SELECT
    waiter.application_name AS waiter_application,
    blocker.application_name AS blocker_application,
    waiter.wait_event_type,
    waiter.wait_event,
    lock_catalog.mode AS requested_mode,
    lock_catalog.granted
FROM pg_catalog.pg_stat_activity AS waiter
CROSS JOIN LATERAL pg_catalog.unnest(
    pg_catalog.pg_blocking_pids(waiter.pid)
) AS blocker_pid(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
  ON blocker.pid = blocker_pid.pid
JOIN pg_catalog.pg_locks AS lock_catalog
  ON lock_catalog.pid = waiter.pid
 AND lock_catalog.relation =
     'shop_private.ch11_order'::regclass
 AND NOT lock_catalog.granted
WHERE waiter.application_name = 'pg36-ch11-lock-waiter'
  AND blocker.application_name = 'pg36-ch11-lock-holder'
ORDER BY lock_catalog.mode;
"""
        deadline = time.monotonic() + 3.5
        while time.monotonic() < deadline and not graph_rows:
            graph = run_psql(
                args.service,
                "pg36-ch11-lock-observer",
                graph_sql,
                csv_output=True,
            )
            if graph.returncode != 0:
                raise LockCaseError(
                    f"lock graph query failed: {graph.stderr}"
                )
            graph_document = graph.stdout
            graph_rows = parse_csv_rows(graph_document)
            if not graph_rows:
                time.sleep(0.04)

        waiter_stdout, waiter_stderr = waiter.communicate(timeout=12)
        (evidence / "lock-attempt.stdout").write_text(
            waiter_stdout,
            encoding="utf-8",
        )
        (evidence / "lock-attempt.stderr").write_text(
            waiter_stderr,
            encoding="utf-8",
        )
        (evidence / "lock-graph.csv").write_text(
            graph_document,
            encoding="utf-8",
        )

        if waiter.returncode != 3:
            raise LockCaseError(
                f"lock attempt exited {waiter.returncode}, expected 3"
            )
        if not re.search(r"\b55P03\b", waiter_stderr):
            raise LockCaseError("lock attempt did not expose SQLSTATE 55P03")
        if len(graph_rows) != 1:
            raise LockCaseError(
                f"expected one waiter/blocker edge, got {len(graph_rows)}"
            )
        edge = graph_rows[0]
        if (
            edge["wait_event_type"] != "Lock"
            or edge["requested_mode"] != "AccessExclusiveLock"
            or edge["granted"] != "f"
        ):
            raise LockCaseError(f"unexpected lock edge: {edge}")

        column = run_psql(
            args.service,
            "pg36-ch11-lock-observer",
            """
SELECT count(*)
FROM pg_catalog.pg_attribute
WHERE attrelid = 'shop_private.ch11_order'::regclass
  AND attname = 'shipping_code'
  AND attnum > 0
  AND NOT attisdropped;
""",
        )
        if column.returncode != 0 or column.stdout.strip() != "0":
            raise LockCaseError(
                "failed ADD COLUMN changed the schema unexpectedly"
            )

        holder.stdin.write("COMMIT;\n\\echo CH11_HOLDER_RELEASED\n\\quit\n")
        holder.stdin.flush()
        released_lines = wait_for_marker(
            holder,
            "CH11_HOLDER_RELEASED",
            5.0,
        )
        holder_lines.extend(released_lines)
        holder_stdout, holder_stderr = holder.communicate(timeout=5)
        holder_lines.append(holder_stdout)
        (evidence / "lock-holder.stdout").write_text(
            "".join(holder_lines),
            encoding="utf-8",
        )
        (evidence / "lock-holder.stderr").write_text(
            holder_stderr,
            encoding="utf-8",
        )
        if holder.returncode != 0:
            raise LockCaseError(
                f"holder exited {holder.returncode}: {holder_stderr}"
            )

        result = {
            "schema": "pg36-ch11-lock-result-v1",
            "status": "ok",
            "sqlstate": "55P03",
            "waiter": "pg36-ch11-lock-waiter",
            "blocker": "pg36-ch11-lock-holder",
            "requested_mode": "AccessExclusiveLock",
            "blocker_edges": 1,
            "column_absent_after_failure": True,
            "holder_released_by": "COMMIT",
        }
        (evidence / "lock-summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            "lock=55P03/edge:1/"
            "requested:AccessExclusiveLock/column-absent"
        )
        return 0
    except (
        LockCaseError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ch11 lock case failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if holder is not None and holder.poll() is None:
            if holder.stdin is not None:
                try:
                    holder.stdin.write("ROLLBACK;\n\\quit\n")
                    holder.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            try:
                holder.wait(timeout=3)
            except subprocess.TimeoutExpired:
                holder.terminate()
                try:
                    holder.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    holder.kill()


if __name__ == "__main__":
    raise SystemExit(main())
