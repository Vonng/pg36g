#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExperimentError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(0o600)


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "PAGER": "cat",
            "PSQL_PAGER": "cat",
            "PGCONNECT_TIMEOUT": "5",
        }
    )
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        raise ExperimentError(
            f"command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"{completed.stderr[-3000:]}"
        )
    return completed


def command_version(binary: Path) -> str:
    completed = run([str(binary), "--version"])
    return completed.stdout.strip()


def parse_major(version: str) -> int:
    match = re.search(r"^(?:postgres\s+\(PostgreSQL\)\s+)?(\d+)", version)
    if not match:
        raise ExperimentError(f"cannot parse PostgreSQL major from {version!r}")
    return int(match.group(1))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def psql(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
    database: str,
    sql: str,
    *,
    tuples_only: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(binary_dir / "psql"),
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "--no-psqlrc",
        "-h",
        str(socket_dir),
        "-p",
        str(port),
        "-U",
        "postgres",
        "-d",
        database,
    ]
    if tuples_only:
        command.extend(["-A", "-t"])
    return run(command, input_text=sql, check=check)


def json_psql(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
    database: str,
    sql: str,
) -> Any:
    completed = psql(
        binary_dir,
        socket_dir,
        port,
        database,
        sql,
        tuples_only=True,
    )
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    for row in reversed(rows):
        try:
            return json.loads(row)
        except json.JSONDecodeError:
            continue
    raise ExperimentError(f"query did not return JSON: {completed.stdout[-1000:]}")


def explain_json(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
    database: str,
) -> Any:
    completed = psql(
        binary_dir,
        socket_dir,
        port,
        database,
        """
EXPLAIN (FORMAT JSON, COSTS OFF)
SELECT order_id, amount, status
FROM app.orders
WHERE order_code = 'order-5000';
""",
        tuples_only=True,
    )
    return json.loads(completed.stdout.strip())


def manifest(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
WITH status_counts AS (
  SELECT jsonb_object_agg(status, n ORDER BY status) AS value
  FROM (
    SELECT status, count(*) AS n
    FROM app.orders
    GROUP BY status
  ) AS s
)
SELECT jsonb_build_object(
  'rows', count(*),
  'min_id', min(order_id),
  'max_id', max(order_id),
  'amount_sum', sum(amount)::text,
  'ordered_digest_md5',
    md5(string_agg(
      order_id::text || ':' ||
      order_code || ':' ||
      amount::text || ':' ||
      status || ':' ||
      to_char(created_at AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US'),
      '|' ORDER BY order_id
    )),
  'status_counts', (SELECT value FROM status_counts),
  'invalid_statuses',
    count(*) FILTER (
      WHERE status NOT IN ('new', 'paid', 'shipped')
    ),
  'negative_amounts', count(*) FILTER (WHERE amount < 0)
)
FROM app.orders;
""",
    )


def identity(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
SELECT jsonb_build_object(
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'system_identifier',
    (SELECT system_identifier FROM pg_control_system()),
  'data_checksums', current_setting('data_checksums'),
  'database', current_database(),
  'in_recovery', pg_is_in_recovery()
);
""",
    )


def extension_manifest(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> list[dict[str, Any]]:
    value = json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
SELECT coalesce(
  jsonb_agg(
    jsonb_build_object(
      'name', extname,
      'version', extversion,
      'schema', extnamespace::regnamespace::text
    )
    ORDER BY extname
  ),
  '[]'::jsonb
)
FROM pg_extension;
""",
    )
    if not isinstance(value, list):
        raise ExperimentError("extension manifest is not a list")
    return value


def selected_settings(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
SELECT jsonb_object_agg(name, setting ORDER BY name)
FROM pg_settings
WHERE name IN (
  'block_size',
  'data_checksums',
  'default_text_search_config',
  'lc_messages',
  'lc_monetary',
  'lc_numeric',
  'lc_time',
  'max_connections',
  'server_encoding',
  'shared_buffers',
  'wal_block_size',
  'wal_segment_size'
);
""",
    )


def collation_state(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
WITH target AS (
  SELECT oid,
         oid::regcollation::text AS name,
         collprovider,
         collversion,
         pg_collation_actual_version(oid) AS actual_version
  FROM pg_collation
  WHERE oid = 'app.en_numeric'::regcollation
),
indexes AS (
  SELECT coalesce(
           jsonb_agg(indexrelid::regclass::text ORDER BY indexrelid::regclass::text),
           '[]'::jsonb
         ) AS names
  FROM pg_index, target
  WHERE target.oid = ANY(pg_index.indcollation)
)
SELECT jsonb_build_object(
  'name', target.name,
  'provider', target.collprovider,
  'recorded_version', target.collversion,
  'actual_version', target.actual_version,
  'mismatch',
    target.collversion IS DISTINCT FROM target.actual_version,
  'affected_indexes', indexes.names
)
FROM target, indexes;
""",
    )


def health_state(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
SELECT jsonb_build_object(
  'invalid_indexes',
    (SELECT count(*) FROM pg_index WHERE NOT indisvalid OR NOT indisready),
  'prepared_transactions',
    (SELECT count(*) FROM pg_prepared_xacts),
  'active_nonself_sessions',
    (SELECT count(*)
     FROM pg_stat_activity
     WHERE pid <> pg_backend_pid()
       AND datname = current_database())
);
""",
    )


def query_result(
    binary_dir: Path,
    socket_dir: Path,
    port: int,
) -> dict[str, Any]:
    return json_psql(
        binary_dir,
        socket_dir,
        port,
        "pg36_upgrade",
        """
SELECT to_jsonb(q)
FROM (
  SELECT order_id, order_code, amount::text, status,
         to_char(created_at AT TIME ZONE 'UTC',
                 'YYYY-MM-DD"T"HH24:MI:SS.US') AS created_at_utc
  FROM app.orders
  WHERE order_code = 'order-5000'
) AS q;
""",
    )


def host_identity(service: str) -> dict[str, Any]:
    completed = run(
        [
            "psql",
            "-X",
            "-w",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "--no-psqlrc",
            "-d",
            f"service={service} dbname=postgres "
            "application_name=pg36-ch30-host-proof",
            "-c",
            """
SELECT jsonb_build_object(
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'system_identifier',
    (SELECT system_identifier FROM pg_control_system()),
  'in_recovery', pg_is_in_recovery()
);
""",
        ]
    )
    return json.loads(completed.stdout.strip())


class TempCluster:
    def __init__(
        self,
        binary_dir: Path,
        data_dir: Path,
        socket_dir: Path,
        port: int,
        log_path: Path,
    ) -> None:
        self.binary_dir = binary_dir
        self.data_dir = data_dir
        self.socket_dir = socket_dir
        self.port = port
        self.log_path = log_path
        self.started = False

    def start(self) -> None:
        if self.started:
            raise ExperimentError(f"cluster already started: {self.data_dir}")
        options = (
            f"-k {self.socket_dir} -p {self.port} "
            "-c listen_addresses='' "
            "-c unix_socket_permissions=0700 "
            "-c fsync=on -c full_page_writes=on"
        )
        run(
            [
                str(self.binary_dir / "pg_ctl"),
                "-D",
                str(self.data_dir),
                "-l",
                str(self.log_path),
                "-o",
                options,
                "-w",
                "start",
            ],
            timeout=60,
        )
        self.started = True

    def stop(self) -> None:
        if not self.started:
            return
        completed = run(
            [
                str(self.binary_dir / "pg_ctl"),
                "-D",
                str(self.data_dir),
                "-m",
                "fast",
                "-w",
                "stop",
            ],
            check=False,
            timeout=60,
        )
        self.started = False
        if completed.returncode != 0:
            raise ExperimentError(
                f"failed to stop temporary cluster {self.data_dir}: "
                f"{completed.stderr[-2000:]}"
            )


def require_private_path(path: Path, parent: Path, label: str) -> None:
    resolved = path.resolve()
    parent_resolved = parent.resolve()
    if resolved == parent_resolved or parent_resolved not in resolved.parents:
        raise ExperimentError(f"{label} escapes marker root: {resolved}")


def init_cluster(
    initdb: Path,
    data_dir: Path,
    *,
    share_dir: Path | None,
    checksums: bool,
) -> None:
    command = [
        str(initdb),
        "-D",
        str(data_dir),
        "--locale=C",
        "--encoding=UTF8",
        "-U",
        "postgres",
        "--auth=trust",
    ]
    if share_dir is not None:
        command.extend(["-L", str(share_dir)])
    command.append("--data-checksums" if checksums else "--no-data-checksums")
    run(command, timeout=120)


def pg_upgrade_command(
    new_bin: Path,
    old_bin: Path,
    old_data: Path,
    new_data: Path,
    socket_dir: Path,
    old_port: int,
    new_port: int,
    *,
    check_only: bool,
) -> list[str]:
    command = [
        str(new_bin / "pg_upgrade"),
        "-b",
        str(old_bin),
        "-B",
        str(new_bin),
        "-d",
        str(old_data),
        "-D",
        str(new_data),
        "-p",
        str(old_port),
        "-P",
        str(new_port),
        "-s",
        str(socket_dir),
        "-U",
        "postgres",
    ]
    if check_only:
        command.append("--check")
    else:
        command.append("--copy")
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--marker-file", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--preflight-run-id", required=True)
    parser.add_argument("--old-bin", required=True, type=Path)
    parser.add_argument("--old-share", required=True, type=Path)
    parser.add_argument("--new-bin", required=True, type=Path)
    args = parser.parse_args()

    requirements = json.loads(args.requirements.read_text())
    contract = json.loads(args.contract.read_text())
    marker = json.loads(args.marker_file.read_text())
    remote_root = args.marker_file.parent.resolve()
    run_root = args.run_root.resolve()
    output_dir = args.output_dir.resolve()

    if (
        marker.get("schema") != "pg36-ch30-remote-marker-v1"
        or marker.get("run_id") != args.run_id
        or not remote_root.name.startswith("pg36-ch30-remote-")
    ):
        raise ExperimentError("remote marker is not valid")
    require_private_path(run_root, remote_root, "run root")
    require_private_path(output_dir, remote_root, "output directory")

    old_bin = args.old_bin.resolve()
    old_share = args.old_share.resolve()
    new_bin = args.new_bin.resolve()
    for required_path in [
        old_bin / "postgres",
        old_bin / "initdb",
        old_bin / "pg_ctl",
        old_bin / "psql",
        old_share / "postgres.bki",
        new_bin / "postgres",
        new_bin / "initdb",
        new_bin / "pg_upgrade",
    ]:
        if not required_path.is_file():
            raise ExperimentError(f"required path missing: {required_path}")

    old_version = command_version(old_bin / "postgres")
    new_version = command_version(new_bin / "postgres")
    if (
        parse_major(old_version) != requirements["versions"]["old_major"]
        or parse_major(new_version) != requirements["versions"]["new_major"]
    ):
        raise ExperimentError("binary major versions do not match requirements")

    run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    socket_dir = run_root / "socket"
    socket_dir.mkdir(mode=0o700)
    work_bad = run_root / "work-bad"
    work_good = run_root / "work-good"
    work_bad.mkdir(mode=0o700)
    work_good.mkdir(mode=0o700)

    old_data = run_root / "old"
    bad_data = run_root / "new-bad"
    new_data = run_root / "new"
    old_port = int(requirements["execution"]["old_port"])
    new_port = int(requirements["execution"]["new_port"])

    old_cluster = TempCluster(
        old_bin,
        old_data,
        socket_dir,
        old_port,
        output_dir / "old-server.log",
    )
    new_cluster = TempCluster(
        new_bin,
        new_data,
        socket_dir,
        new_port,
        output_dir / "new-server.log",
    )

    evidence: dict[str, Any] = {
        "schema": "pg36-ch30-upgrade-evidence-v1",
        "run_id": args.run_id,
        "preflight_run_id": args.preflight_run_id,
        "captured_at": utc_now(),
        "target": requirements["target"],
        "states": [],
    }
    host_before: dict[str, Any] | None = None

    try:
        evidence["states"].append("PREFLIGHT")
        host_before = host_identity(requirements["host"]["service"])
        if (
            host_before.get("cluster_name") != requirements["host"]["cluster"]
            or host_before.get("in_recovery") is not False
        ):
            raise ExperimentError("managed host identity is not acceptable")

        init_cluster(
            old_bin / "initdb",
            old_data,
            share_dir=old_share,
            checksums=True,
        )
        old_cluster.start()

        run(
            [
                str(old_bin / "createdb"),
                "-h",
                str(socket_dir),
                "-p",
                str(old_port),
                "-U",
                "postgres",
                "pg36_upgrade",
            ]
        )
        fixture_sql = """
CREATE SCHEMA app;
CREATE COLLATION app.en_numeric (
  provider = icu,
  locale = 'en-u-kn-true'
);
CREATE TABLE app.orders (
  order_id bigint PRIMARY KEY,
  order_code text COLLATE app.en_numeric NOT NULL UNIQUE,
  amount numeric(12,2) NOT NULL CHECK (amount >= 0),
  status text NOT NULL CHECK (status IN ('new','paid','shipped')),
  created_at timestamptz NOT NULL
);
INSERT INTO app.orders
SELECT i,
       'order-' || i,
       (i % 10000)::numeric / 100,
       (ARRAY['new','paid','shipped'])[1 + i % 3],
       timestamptz '2026-01-01 00:00:00+00'
         + i * interval '1 second'
FROM generate_series(1, 10000) AS g(i);
ANALYZE app.orders;
"""
        psql(
            old_bin,
            socket_dir,
            old_port,
            "pg36_upgrade",
            fixture_sql,
        )
        source_baseline = {
            "identity": identity(old_bin, socket_dir, old_port),
            "manifest": manifest(old_bin, socket_dir, old_port),
            "extensions": extension_manifest(
                old_bin, socket_dir, old_port
            ),
            "settings": selected_settings(old_bin, socket_dir, old_port),
            "collation": collation_state(
                old_bin, socket_dir, old_port
            ),
            "health": health_state(old_bin, socket_dir, old_port),
            "query_result": query_result(
                old_bin, socket_dir, old_port
            ),
            "query_plan": explain_json(
                old_bin, socket_dir, old_port, "pg36_upgrade"
            ),
        }
        if (
            source_baseline["manifest"]["rows"]
            != requirements["fixture"]["initial_rows"]
            or source_baseline["collation"]["mismatch"] is not False
            or source_baseline["health"]["invalid_indexes"] != 0
        ):
            raise ExperimentError("source baseline is not acceptable")
        evidence["states"].append("SOURCE_BASELINE")

        injection_sql = """
UPDATE pg_catalog.pg_collation
SET collversion = 'pg36-injected-stale'
WHERE oid = 'app.en_numeric'::regcollation;
"""
        injection = psql(
            old_bin,
            socket_dir,
            old_port,
            "pg36_upgrade",
            injection_sql,
        )
        if "UPDATE 1" not in injection.stdout:
            raise ExperimentError("collation injection did not update one row")
        mismatch_before = collation_state(
            old_bin, socket_dir, old_port
        )
        expected_index = requirements["fixture"]["collation_index"]
        if (
            mismatch_before["mismatch"] is not True
            or expected_index not in mismatch_before["affected_indexes"]
        ):
            raise ExperimentError("collation release gate did not block")
        evidence["states"].append("COMPATIBILITY_BLOCKED")

        repair_started = utc_now()
        reindex_result = psql(
            old_bin,
            socket_dir,
            old_port,
            "pg36_upgrade",
            "REINDEX INDEX app.orders_order_code_key;\n",
        )
        refresh_result = psql(
            old_bin,
            socket_dir,
            old_port,
            "pg36_upgrade",
            "ALTER COLLATION app.en_numeric REFRESH VERSION;\n",
        )
        mismatch_after = collation_state(
            old_bin, socket_dir, old_port
        )
        source_after_repair = manifest(
            old_bin, socket_dir, old_port
        )
        if (
            "REINDEX" not in reindex_result.stdout
            or "ALTER COLLATION" not in refresh_result.stdout
            or mismatch_after["mismatch"] is not False
            or source_after_repair != source_baseline["manifest"]
        ):
            raise ExperimentError("collation repair did not converge")
        evidence["states"].append("COMPATIBILITY_REPAIRED")

        old_cluster.stop()
        evidence["states"].append("SOURCE_STOPPED")
        source_checksum_check = run(
            [
                str(old_bin / "pg_checksums"),
                "--check",
                "-D",
                str(old_data),
            ]
        )
        write_text(
            output_dir / "source-checksums.log",
            source_checksum_check.stdout + source_checksum_check.stderr,
        )

        init_cluster(
            new_bin / "initdb",
            bad_data,
            share_dir=None,
            checksums=False,
        )
        bad_check_started = time.monotonic()
        bad_check = run(
            pg_upgrade_command(
                new_bin,
                old_bin,
                old_data,
                bad_data,
                socket_dir,
                old_port,
                new_port,
                check_only=True,
            ),
            cwd=work_bad,
            check=False,
            timeout=180,
        )
        bad_check_seconds = time.monotonic() - bad_check_started
        bad_log = bad_check.stdout + bad_check.stderr
        write_text(output_dir / "pg-upgrade-check-rejected.log", bad_log)
        expected_failure = (
            "old cluster uses data checksums but the new one does not"
        )
        if bad_check.returncode == 0 or expected_failure not in bad_log:
            raise ExperimentError("checksum-incompatible check was not rejected")
        evidence["states"].append("CHECK_REJECTED")
        require_private_path(bad_data, run_root, "bad target")
        shutil.rmtree(bad_data)

        init_cluster(
            new_bin / "initdb",
            new_data,
            share_dir=None,
            checksums=True,
        )
        good_check_started = time.monotonic()
        good_check = run(
            pg_upgrade_command(
                new_bin,
                old_bin,
                old_data,
                new_data,
                socket_dir,
                old_port,
                new_port,
                check_only=True,
            ),
            cwd=work_good,
            check=False,
            timeout=180,
        )
        good_check_seconds = time.monotonic() - good_check_started
        good_log = good_check.stdout + good_check.stderr
        write_text(output_dir / "pg-upgrade-check-passed.log", good_log)
        if (
            good_check.returncode != 0
            or "*Clusters are compatible*" not in good_log
        ):
            raise ExperimentError("matching pg_upgrade check did not pass")
        evidence["states"].append("CHECK_PASSED")

        upgrade_started = time.monotonic()
        upgrade = run(
            pg_upgrade_command(
                new_bin,
                old_bin,
                old_data,
                new_data,
                socket_dir,
                old_port,
                new_port,
                check_only=False,
            ),
            cwd=work_good,
            check=False,
            timeout=300,
        )
        upgrade_seconds = time.monotonic() - upgrade_started
        upgrade_log = upgrade.stdout + upgrade.stderr
        write_text(output_dir / "pg-upgrade-copy.log", upgrade_log)
        if (
            upgrade.returncode != 0
            or "Upgrade Complete" not in upgrade_log
        ):
            raise ExperimentError("pg_upgrade --copy did not complete")
        evidence["states"].append("UPGRADED")

        new_cluster.start()
        upgraded_before_writes = {
            "identity": identity(new_bin, socket_dir, new_port),
            "manifest": manifest(new_bin, socket_dir, new_port),
            "extensions": extension_manifest(
                new_bin, socket_dir, new_port
            ),
            "settings": selected_settings(new_bin, socket_dir, new_port),
            "collation": collation_state(
                new_bin, socket_dir, new_port
            ),
            "health": health_state(new_bin, socket_dir, new_port),
            "query_result": query_result(
                new_bin, socket_dir, new_port
            ),
            "query_plan": explain_json(
                new_bin, socket_dir, new_port, "pg36_upgrade"
            ),
        }
        if (
            upgraded_before_writes["manifest"]
            != source_after_repair
            or upgraded_before_writes["extensions"]
            != source_baseline["extensions"]
            or upgraded_before_writes["collation"]["mismatch"] is not False
            or upgraded_before_writes["health"]["invalid_indexes"] != 0
            or upgraded_before_writes["query_result"]
            != source_baseline["query_result"]
        ):
            raise ExperimentError("upgraded cluster validation failed")

        psql(
            new_bin,
            socket_dir,
            new_port,
            "pg36_upgrade",
            """
CREATE EXTENSION amcheck;
SELECT bt_index_check('app.orders_pkey'::regclass, true);
SELECT bt_index_check(
  'app.orders_order_code_key'::regclass,
  true
);
""",
        )
        amcheck_indexes = [
            "app.orders_order_code_key",
            "app.orders_pkey",
        ]
        vacuum_missing = run(
            [
                str(new_bin / "vacuumdb"),
                "-h",
                str(socket_dir),
                "-p",
                str(new_port),
                "-U",
                "postgres",
                "--all",
                "--analyze-in-stages",
                "--missing-stats-only",
            ],
            timeout=180,
        )
        vacuum_all = run(
            [
                str(new_bin / "vacuumdb"),
                "-h",
                str(socket_dir),
                "-p",
                str(new_port),
                "-U",
                "postgres",
                "--all",
                "--analyze-only",
            ],
            timeout=180,
        )
        write_text(
            output_dir / "post-upgrade-analyze.log",
            vacuum_missing.stdout
            + vacuum_missing.stderr
            + vacuum_all.stdout
            + vacuum_all.stderr,
        )
        evidence["states"].append("VALIDATED")

        new_cluster.stop()
        old_cluster.start()
        rollback_manifest = manifest(old_bin, socket_dir, old_port)
        rollback_identity = identity(old_bin, socket_dir, old_port)
        rollback_collation = collation_state(
            old_bin, socket_dir, old_port
        )
        rollback_canary_count = json_psql(
            old_bin,
            socket_dir,
            old_port,
            "pg36_upgrade",
            """
SELECT jsonb_build_object(
  'canary_rows',
  count(*) FILTER (WHERE order_id = 10001)
)
FROM app.orders;
""",
        )
        if (
            rollback_manifest != source_after_repair
            or rollback_collation["mismatch"] is not False
            or rollback_canary_count["canary_rows"] != 0
            or parse_major(rollback_identity["server_version"]) != 17
        ):
            raise ExperimentError("old cluster rollback proof failed")
        old_cluster.stop()
        evidence["states"].append("ROLLBACK_PROVEN")

        new_cluster.start()
        psql(
            new_bin,
            socket_dir,
            new_port,
            "pg36_upgrade",
            """
INSERT INTO app.orders (
  order_id, order_code, amount, status, created_at
)
VALUES (
  10001, 'order-10001', 100.01, 'new',
  timestamptz '2026-01-02 00:00:00+00'
);
""",
        )
        forward_manifest = manifest(new_bin, socket_dir, new_port)
        forward_canary = json_psql(
            new_bin,
            socket_dir,
            new_port,
            "pg36_upgrade",
            """
SELECT jsonb_build_object(
  'canary_rows',
  count(*) FILTER (WHERE order_id = 10001)
)
FROM app.orders;
""",
        )
        if (
            forward_manifest["rows"]
            != requirements["fixture"]["forward_canary_id"]
            or forward_canary["canary_rows"] != 1
        ):
            raise ExperimentError("forward canary was not committed")
        new_cluster.stop()
        evidence["states"].append("FORWARD_COMMITTED")

        host_after = host_identity(requirements["host"]["service"])
        if host_after != host_before:
            raise ExperimentError("managed Pigsty host identity changed")

        generated_scripts = sorted(
            path.name
            for path in work_good.iterdir()
            if path.is_file()
        )
        evidence.update(
            {
                "environment": {
                    "old_postgresql": old_version,
                    "new_postgresql": new_version,
                    "old_major": parse_major(old_version),
                    "new_major": parse_major(new_version),
                    "old_postgres_sha256": sha256_file(
                        old_bin / "postgres"
                    ),
                    "new_pg_upgrade_sha256": sha256_file(
                        new_bin / "pg_upgrade"
                    ),
                    "host_before": host_before,
                    "host_after": host_after,
                    "unix_socket_only": True,
                    "listen_addresses": "",
                },
                "source": {
                    "baseline": source_baseline,
                    "manifest_after_repair": source_after_repair,
                    "checksum_check_passed": True,
                },
                "collation_gate": {
                    "injection": "exact-disposable-collversion-row",
                    "injected_value": "pg36-injected-stale",
                    "state_before": mismatch_before,
                    "release_before": "blocked",
                    "repair_started_at": repair_started,
                    "repair_order": [
                        "REINDEX INDEX app.orders_order_code_key",
                        "ALTER COLLATION app.en_numeric REFRESH VERSION",
                    ],
                    "reindex_completed": True,
                    "refresh_completed": True,
                    "state_after": mismatch_after,
                    "release_after": "eligible-for-upgrade-check",
                },
                "incompatible_target": {
                    "old_checksums": True,
                    "new_checksums": False,
                    "check_returncode": bad_check.returncode,
                    "check_seconds": round(bad_check_seconds, 6),
                    "expected_failure": expected_failure,
                    "expected_failure_observed": True,
                    "target_removed": not bad_data.exists(),
                },
                "upgrade": {
                    "method": "copy",
                    "check_returncode": good_check.returncode,
                    "check_seconds": round(good_check_seconds, 6),
                    "check_passed": True,
                    "run_returncode": upgrade.returncode,
                    "run_seconds": round(upgrade_seconds, 6),
                    "complete": True,
                    "manifest_equal_before_writes":
                        upgraded_before_writes["manifest"]
                        == source_after_repair,
                    "extension_manifest_equal_before_amcheck":
                        upgraded_before_writes["extensions"]
                        == source_baseline["extensions"],
                    "query_result_equal":
                        upgraded_before_writes["query_result"]
                        == source_baseline["query_result"],
                    "source_plan":
                        source_baseline["query_plan"],
                    "target_plan":
                        upgraded_before_writes["query_plan"],
                    "upgraded_before_writes":
                        upgraded_before_writes,
                    "amcheck_indexes": amcheck_indexes,
                    "amcheck_passed": True,
                    "post_upgrade_analyze_completed": True,
                    "generated_scripts": generated_scripts,
                },
                "rollback": {
                    "new_cluster_stopped_before_old_start": True,
                    "target_only_writes_before_proof": 0,
                    "old_cluster_restarted": True,
                    "old_major": parse_major(
                        rollback_identity["server_version"]
                    ),
                    "manifest": rollback_manifest,
                    "manifest_equal": rollback_manifest
                    == source_after_repair,
                    "collation_match": rollback_collation[
                        "mismatch"
                    ]
                    is False,
                    "proven_before_target_writes": True,
                },
                "forward": {
                    "old_cluster_stopped": True,
                    "new_cluster_restarted": True,
                    "canary_order_id":
                        requirements["fixture"][
                            "forward_canary_id"
                        ],
                    "canary_rows": forward_canary["canary_rows"],
                    "manifest": forward_manifest,
                    "rollback_requires_reconciliation": True,
                },
                "risk": {
                    "production_data_touched": False,
                    "production_traffic_touched": False,
                    "pigsty_inventory_changed": False,
                    "patroni_configuration_changed": False,
                    "persistent_cluster_configuration_change": False,
                    "system_package_changed": False,
                    "external_listener_created": False,
                    "link_clone_swap_used": False,
                    "delete_old_cluster_script_run": False,
                    "unrelated_process_terminated": False,
                },
                "decision": {
                    "result":
                        "isolated-pg17-to-pg18-state-machine-demonstrated",
                    "production_approval": None,
                    "production_ch30_gate": "pending",
                },
            }
        )

        for cluster in [new_cluster, old_cluster]:
            if cluster.started:
                cluster.stop()
        require_private_path(run_root, remote_root, "final run root")
        shutil.rmtree(run_root)
        fixture_cleanup = {
            "schema": "pg36-ch30-fixture-cleanup-v1",
            "run_id": args.run_id,
            "captured_at": utc_now(),
            "run_root_absent": not run_root.exists(),
            "temporary_postmasters_stopped": True,
            "managed_host_identity_unchanged": host_after == host_before,
            "unrelated_processes_terminated": 0,
            "ordinary_directory_removal": True,
        }
        evidence["states"].append("CLEANED")
        evidence["captured_at"] = utc_now()
        write_json(output_dir / "upgrade-evidence.json", evidence)
        write_json(output_dir / "fixture-cleanup.json", fixture_cleanup)
        return 0
    except Exception as exc:
        failure = {
            "schema": "pg36-ch30-failure-v1",
            "run_id": args.run_id,
            "captured_at": utc_now(),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "states": evidence.get("states", []),
        }
        write_json(output_dir / "failure.json", failure)
        raise
    finally:
        for cluster in [new_cluster, old_cluster]:
            if cluster.started:
                try:
                    cluster.stop()
                except Exception:
                    pass


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    raise SystemExit(main())
