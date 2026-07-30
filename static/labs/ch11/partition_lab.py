#!/usr/bin/env python3
"""Measure ATTACH locks and exercise PG14+ DETACH CONCURRENTLY."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class PartitionLabError(RuntimeError):
    pass


def base(service: str, app: str) -> list[str]:
    return [
        "psql",
        "-X",
        "-w",
        "-qAt",
        f"--dbname=service={service} application_name={app}",
        "--set=ON_ERROR_STOP=1",
    ]


def run(
    service: str,
    app: str,
    sql: str | None = None,
    file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = base(service, app)
    if sql is not None:
        command.extend(["--command", sql])
    if file is not None:
        command.extend(["--file", str(file)])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PSQLRC": os.devnull},
    )


def run_commands(
    service: str,
    app: str,
    commands: list[str],
) -> subprocess.CompletedProcess[str]:
    command = base(service, app)
    for sql in commands:
        command.extend(["--command", sql])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PSQLRC": os.devnull},
    )


def require_success(
    completed: subprocess.CompletedProcess[str],
    label: str,
) -> None:
    if completed.returncode != 0:
        raise PartitionLabError(
            f"{label} failed: {completed.stderr.strip()}"
        )


def query_json(service: str, app: str, expression: str) -> Any:
    completed = run(service, app, sql=expression)
    require_success(completed, app)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PartitionLabError(
            f"{app} returned non-JSON: {completed.stdout!r}"
        ) from exc


def catalog(service: str, app: str) -> dict[str, Any]:
    sql = """
SELECT pg_catalog.json_build_object(
    'server_version_num',
        current_setting('server_version_num')::integer,
    'child_filenode',
        pg_catalog.pg_relation_filenode(
            'shop_private.ch11_event_2025q1'::regclass
        ),
    'child_bytes',
        pg_catalog.pg_relation_size(
            'shop_private.ch11_event_2025q1'::regclass
        ),
    'child_rows',
        (SELECT count(*)
         FROM shop_private.ch11_event_2025q1),
    'parent_rows',
        (SELECT count(*)
         FROM shop_private.ch11_event),
    'is_partition',
        (SELECT relispartition
         FROM pg_catalog.pg_class
         WHERE oid =
               'shop_private.ch11_event_2025q1'::regclass),
    'parent_links',
        (SELECT count(*)
         FROM pg_catalog.pg_inherits
         WHERE inhrelid =
               'shop_private.ch11_event_2025q1'::regclass
           AND inhparent =
               'shop_private.ch11_event'::regclass),
    'bound_check_valid',
        (SELECT convalidated
         FROM pg_catalog.pg_constraint
         WHERE conrelid =
               'shop_private.ch11_event_2025q1'::regclass
           AND conname = 'ch11_event_2025q1_bound')
);
"""
    value = query_json(service, app, sql)
    if not isinstance(value, dict):
        raise PartitionLabError("partition catalog is not an object")
    return value


def wait_marker(
    process: subprocess.Popen[str],
    marker: str,
    timeout: float,
) -> None:
    if process.stdout is None:
        raise PartitionLabError("attach holder stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise PartitionLabError(
                f"attach holder exited before {marker}"
            )
        events = selector.select(max(0.0, deadline - time.monotonic()))
        if not events:
            continue
        line = process.stdout.readline()
        if marker in line:
            return
    raise PartitionLabError(f"timed out waiting for {marker}")


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

    try:
        prepared = run(
            args.service,
            "pg36-ch11-partition-prepare",
            file=args.script_dir / "partition-prepare.sql",
        )
        require_success(prepared, "partition prepare")
        (evidence / "partition-prepare.txt").write_text(
            prepared.stdout,
            encoding="utf-8",
        )
        (evidence / "partition-prepare.stderr").write_text(
            prepared.stderr,
            encoding="utf-8",
        )

        before = catalog(
            args.service,
            "pg36-ch11-partition-before",
        )
        if (
            before["is_partition"]
            or before["parent_links"] != 0
            or before["child_rows"] != 20000
            or before["parent_rows"] != 0
            or before["bound_check_valid"] is not True
        ):
            raise PartitionLabError(
                f"unexpected pre-attach catalog: {before}"
            )

        holder = subprocess.Popen(
            base(args.service, "pg36-ch11-partition-attach"),
            cwd=args.script_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "PSQLRC": os.devnull},
        )
        if holder.stdin is None:
            raise PartitionLabError("attach holder stdin unavailable")
        holder.stdin.write(
            "\\set ON_ERROR_STOP on\n"
            "\\ir context.sql\n"
            "BEGIN;\n"
            "ALTER TABLE shop_private.ch11_event "
            "ATTACH PARTITION shop_private.ch11_event_2025q1 "
            "FOR VALUES FROM ('2025-01-01 00:00:00+00') "
            "TO ('2025-04-01 00:00:00+00');\n"
            "\\echo CH11_ATTACH_READY\n"
        )
        holder.stdin.flush()
        wait_marker(holder, "CH11_ATTACH_READY", 15.0)

        locks_sql = """
SELECT pg_catalog.json_agg(lock_row ORDER BY relation_name, mode)
FROM (
    SELECT
        lock_catalog.relation::regclass::text AS relation_name,
        lock_catalog.mode,
        lock_catalog.granted
    FROM pg_catalog.pg_locks AS lock_catalog
    JOIN pg_catalog.pg_stat_activity AS activity
      ON activity.pid = lock_catalog.pid
    WHERE activity.application_name =
          'pg36-ch11-partition-attach'
      AND lock_catalog.relation IN (
          'shop_private.ch11_event'::regclass,
          'shop_private.ch11_event_2025q1'::regclass
      )
) AS lock_row;
"""
        locks = query_json(
            args.service,
            "pg36-ch11-partition-observer",
            locks_sql,
        )
        if not isinstance(locks, list):
            raise PartitionLabError("attach lock evidence is not a list")
        lock_pairs = {
            (row["relation_name"], row["mode"])
            for row in locks
            if row.get("granted") is True
        }
        expected_pairs = {
            (
                "shop_private.ch11_event",
                "ShareUpdateExclusiveLock",
            ),
            (
                "shop_private.ch11_event_2025q1",
                "AccessExclusiveLock",
            ),
        }
        if not expected_pairs.issubset(lock_pairs):
            raise PartitionLabError(
                f"ATTACH lock relationship drifted: {locks}"
            )

        holder.stdin.write("COMMIT;\n\\quit\n")
        holder.stdin.flush()
        holder_stdout, holder_stderr = holder.communicate(timeout=8)
        (evidence / "partition-attach-holder.txt").write_text(
            holder_stdout,
            encoding="utf-8",
        )
        (evidence / "partition-attach-holder.stderr").write_text(
            holder_stderr,
            encoding="utf-8",
        )
        if holder.returncode != 0:
            raise PartitionLabError(
                f"attach holder failed: {holder_stderr}"
            )

        after_attach = catalog(
            args.service,
            "pg36-ch11-partition-after-attach",
        )
        if (
            after_attach["is_partition"] is not True
            or after_attach["parent_links"] != 1
            or after_attach["parent_rows"] != 20000
            or after_attach["child_filenode"]
            != before["child_filenode"]
        ):
            raise PartitionLabError(
                f"unexpected post-attach catalog: {after_attach}"
            )

        version = int(after_attach["server_version_num"])
        if version < 140000:
            raise PartitionLabError(
                "DETACH CONCURRENTLY requires PostgreSQL 14+"
            )

        detach_started = time.monotonic()
        detached_command = run_commands(
            args.service,
            "pg36-ch11-partition-detach",
            [
                "SET ROLE pg36_owner",
                "ALTER TABLE shop_private.ch11_event "
                "DETACH PARTITION "
                "shop_private.ch11_event_2025q1 CONCURRENTLY",
            ],
        )
        detach_ms = round(
            (time.monotonic() - detach_started) * 1000,
            3,
        )
        require_success(detached_command, "DETACH CONCURRENTLY")
        (evidence / "partition-detach.txt").write_text(
            detached_command.stdout,
            encoding="utf-8",
        )
        (evidence / "partition-detach.stderr").write_text(
            detached_command.stderr,
            encoding="utf-8",
        )

        after_detach = catalog(
            args.service,
            "pg36-ch11-partition-after-detach",
        )
        if (
            after_detach["is_partition"]
            or after_detach["parent_links"] != 0
            or after_detach["parent_rows"] != 0
            or after_detach["child_rows"] != 20000
            or after_detach["child_filenode"]
            != before["child_filenode"]
        ):
            raise PartitionLabError(
                f"unexpected post-detach catalog: {after_detach}"
            )

        reattach = run_commands(
            args.service,
            "pg36-ch11-partition-reattach",
            [
                "SET ROLE pg36_owner",
                "ALTER TABLE shop_private.ch11_event "
                "ATTACH PARTITION "
                "shop_private.ch11_event_2025q1 "
                "FOR VALUES FROM ('2025-01-01 00:00:00+00') "
                "TO ('2025-04-01 00:00:00+00')",
            ],
        )
        require_success(reattach, "partition reattach")
        final = catalog(
            args.service,
            "pg36-ch11-partition-final",
        )
        if (
            final["is_partition"] is not True
            or final["parent_links"] != 1
            or final["parent_rows"] != 20000
            or final["child_filenode"] != before["child_filenode"]
        ):
            raise PartitionLabError(
                f"unexpected final partition catalog: {final}"
            )

        result = {
            "schema": "pg36-ch11-partition-result-v1",
            "status": "ok",
            "before": before,
            "attach_locks": locks,
            "after_attach": after_attach,
            "detach": {
                "supported_since": 140000,
                "server_version_num": version,
                "outside_transaction_block": True,
                "elapsed_ms_observed": detach_ms,
            },
            "after_detach": after_detach,
            "final": final,
            "validated_check_present_before_attach": True,
            "filenode_preserved_across_attach_detach": True,
            "data_retained_after_detach": True,
            "reattached_for_final_state": True,
        }
        (evidence / "partition-summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            "partition=attach-locks:SUE+AX/"
            "detach-concurrently:pg14+/"
            "rows-retained:20000/reattached"
        )
        return 0
    except (
        OSError,
        PartitionLabError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ch11 partition lab failed: {exc}", file=sys.stderr)
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
