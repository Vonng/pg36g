#!/usr/bin/env python3
"""Run an atomic, keyset-paginated, resumable ch11 backfill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class BackfillError(RuntimeError):
    pass


def snapshot(service: str) -> dict[str, Any]:
    sql = """
SET ROLE pg36_owner;
SET search_path = pg_catalog, shop_private;
SELECT pg_catalog.json_build_object(
    'phase', state.phase,
    'target_rows', state.target_rows,
    'rows_migrated', state.rows_migrated,
    'batches', state.batches,
    'last_order_id', state.last_order_id,
    'remaining_nulls', (
        SELECT count(*)
        FROM shop_private.ch11_order
        WHERE shipping_code IS NULL
    ),
    'mismatches', (
        SELECT count(*)
        FROM shop_private.ch11_order
        WHERE shipping_code IS NOT NULL
          AND shipping_code IS DISTINCT FROM
              CASE shipping_method
                  WHEN 'standard' THEN 'STD'
                  WHEN 'express' THEN 'EXP'
                  WHEN 'pickup' THEN 'PUP'
              END
    )
)
FROM shop_private.ch11_migration_state AS state
WHERE state.migration_id = 'shipping-code-v1';
"""
    command = [
        "psql",
        "-X",
        "-w",
        "-qAt",
        f"--dbname=service={service} "
        "application_name=pg36-ch11-backfill-snapshot",
        "--set=ON_ERROR_STOP=1",
        "--command",
        sql,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PSQLRC": os.devnull},
    )
    if completed.returncode != 0:
        raise BackfillError(
            f"cannot read checkpoint: {completed.stderr.strip()}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BackfillError(
            f"checkpoint is not JSON: {completed.stdout!r}"
        ) from exc
    if not isinstance(value, dict):
        raise BackfillError("checkpoint JSON is not an object")
    return value


def run_batch(service: str, batch_size: int) -> dict[str, Any]:
    sql = f"""
BEGIN;
SET LOCAL ROLE pg36_owner;
SET LOCAL search_path = pg_catalog, shop_private;
SET LOCAL lock_timeout = '1500ms';
SET LOCAL statement_timeout = '15s';

DO $guard$
BEGIN
    IF current_database() <> 'pg36_shop'
       OR pg_catalog.pg_is_in_recovery() THEN
        RAISE EXCEPTION 'ch11 backfill target guard failed';
    END IF;
    IF pg_catalog.obj_description(
           'shop_private.ch11_order'::regclass,
           'pg_class'
       ) <> 'pg36 ch11 deterministic release lab; safe to rebuild' THEN
        RAISE EXCEPTION 'ch11 backfill fixture marker drifted';
    END IF;
END
$guard$;

WITH locked_state AS MATERIALIZED (
    SELECT *
    FROM shop_private.ch11_migration_state
    WHERE migration_id = 'shipping-code-v1'
      AND phase IN ('expanded', 'backfilling', 'migrated')
    FOR UPDATE
),
scope AS MATERIALIZED (
    SELECT count(*)::bigint AS remaining_before
    FROM shop_private.ch11_order
    WHERE shipping_code IS NULL
),
batch AS MATERIALIZED (
    SELECT target.order_id
    FROM shop_private.ch11_order AS target
    CROSS JOIN locked_state AS state
    WHERE target.order_id > state.last_order_id
      AND target.shipping_code IS NULL
    ORDER BY target.order_id
    LIMIT {batch_size}
    FOR UPDATE OF target
),
updated AS (
    UPDATE shop_private.ch11_order AS target
       SET shipping_code =
           CASE target.shipping_method
               WHEN 'standard' THEN 'STD'
               WHEN 'express' THEN 'EXP'
               WHEN 'pickup' THEN 'PUP'
           END
      FROM batch
     WHERE target.order_id = batch.order_id
    RETURNING target.order_id
),
aggregate AS (
    SELECT
        count(*)::bigint AS updated_rows,
        COALESCE(max(order_id), 0)::bigint AS max_order_id
    FROM updated
)
UPDATE shop_private.ch11_migration_state AS state
   SET phase = CASE
           WHEN scope.remaining_before =
                aggregate.updated_rows
           THEN 'migrated'
           ELSE 'backfilling'
       END,
       target_rows = COALESCE(
           state.target_rows,
           state.rows_migrated + scope.remaining_before
       ),
       rows_migrated =
           state.rows_migrated + aggregate.updated_rows,
       batches = state.batches +
           CASE WHEN aggregate.updated_rows > 0 THEN 1 ELSE 0 END,
       last_order_id = GREATEST(
           state.last_order_id,
           aggregate.max_order_id
       ),
       migrated_at = CASE
           WHEN scope.remaining_before =
                aggregate.updated_rows
           THEN pg_catalog.clock_timestamp()
           ELSE state.migrated_at
       END,
       updated_at = pg_catalog.clock_timestamp()
  FROM locked_state, scope, aggregate
 WHERE state.migration_id = locked_state.migration_id;

DO $progress_guard$
DECLARE
    unresolved bigint;
    current_phase text;
BEGIN
    SELECT
        phase,
        (
            SELECT count(*)
            FROM shop_private.ch11_order
            WHERE shipping_code IS NULL
              AND order_id <= state.last_order_id
        )
      INTO current_phase, unresolved
      FROM shop_private.ch11_migration_state AS state
     WHERE migration_id = 'shipping-code-v1';

    IF unresolved <> 0 THEN
        RAISE EXCEPTION
            'checkpoint skipped % unresolved rows',
            unresolved;
    END IF;
    IF current_phase IS NULL THEN
        RAISE EXCEPTION
            'backfill checkpoint is missing or in an invalid phase';
    END IF;
END
$progress_guard$;
COMMIT;
"""
    command = [
        "psql",
        "-X",
        "-w",
        "-qAt",
        f"--dbname=service={service} "
        "application_name=pg36-ch11-backfill",
        "--set=ON_ERROR_STOP=1",
        "--command",
        sql,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PSQLRC": os.devnull},
    )
    if completed.returncode != 0:
        raise BackfillError(
            f"batch failed: {completed.stderr.strip()}"
        )
    return snapshot(service)


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default="pg36-admin")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 50000:
        parser.error("--batch-size must be between 1 and 50000")
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("--max-batches must be positive")
    if args.sleep_ms < 0 or args.sleep_ms > 60000:
        parser.error("--sleep-ms must be between 0 and 60000")

    try:
        start = snapshot(args.service)
        if start.get("phase") not in {
            "expanded",
            "backfilling",
            "migrated",
        }:
            raise BackfillError(
                f"cannot backfill from phase {start.get('phase')!r}"
            )
        if int(start.get("mismatches", -1)) != 0:
            raise BackfillError("pre-existing representation mismatch")

        batches_run = 0
        current = start
        while current["phase"] != "migrated":
            current = run_batch(args.service, args.batch_size)
            batches_run += 1
            if int(current["mismatches"]) != 0:
                raise BackfillError("backfill produced a mismatch")
            if current["phase"] == "migrated":
                break
            if (
                args.max_batches is not None
                and batches_run >= args.max_batches
            ):
                result = {
                    "schema": "pg36-ch11-backfill-result-v1",
                    "status": "interrupted",
                    "exit_code": 75,
                    "batch_size": args.batch_size,
                    "batches_run": batches_run,
                    "start": start,
                    "end": current,
                    "resume_from": current["last_order_id"],
                    "committed_batches_preserved": True,
                }
                write_result(args.output, result)
                print(
                    "backfill=interrupted/"
                    f"batches:{batches_run}/"
                    f"remaining:{current['remaining_nulls']}"
                )
                return 75
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000)

        result = {
            "schema": "pg36-ch11-backfill-result-v1",
            "status": "complete",
            "exit_code": 0,
            "batch_size": args.batch_size,
            "batches_run": batches_run,
            "start": start,
            "end": current,
            "resumed": start["phase"] == "backfilling",
            "remaining_nulls": current["remaining_nulls"],
            "mismatches": current["mismatches"],
        }
        write_result(args.output, result)
        print(
            "backfill=complete/"
            f"batches:{batches_run}/"
            f"rows:{current['rows_migrated']}/"
            f"remaining:{current['remaining_nulls']}"
        )
        return 0
    except (BackfillError, OSError, ValueError) as exc:
        result = {
            "schema": "pg36-ch11-backfill-result-v1",
            "status": "error",
            "message": str(exc),
        }
        write_result(args.output, result)
        print(f"ch11 backfill failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
