#!/usr/bin/env python3
"""Capture a read-only, secret-minimized Pigsty context for chapter 31."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaptureError(RuntimeError):
    """Raised when the declared read-only context cannot be captured."""


SOURCE_FILES = [
    "requirements.json",
    "incident-contract.json",
    "scenarios.json",
    "response-template.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read JSON {path}: {exc}") from exc


def write_private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def source_hashes(source_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file():
            raise CaptureError(f"source file missing: {path}")
        result[name] = sha256_file(path)
    return result


def upstream_hashes(
    source_dir: Path,
    upstream_root: Path,
    requirements: dict[str, Any],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for label, relative in requirements.get("upstream", {}).items():
        declared = source_dir / str(relative)
        path = declared.resolve()
        try:
            path.relative_to(upstream_root.resolve())
        except ValueError as exc:
            raise CaptureError(
                f"upstream path escapes labs root: {declared}"
            ) from exc
        if not path.is_file():
            raise CaptureError(f"upstream evidence missing: {path}")
        result[label] = {
            "name": path.name,
            "sha256": sha256_file(path),
        }
    return result


def remote_capture(
    *,
    ssh_user: str,
    bastion: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    script = textwrap.dedent(
        r'''
        import json
        import os
        import platform
        import subprocess
        import sys
        import urllib.request
        from datetime import datetime, timezone
        from pathlib import Path

        service = sys.argv[1]
        expected_cluster = sys.argv[2]
        members = sys.argv[3].split(",")
        stanza = sys.argv[4]

        def command(args, *, timeout=20):
            completed = subprocess.run(
                args,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout,
                env={
                    **os.environ,
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PAGER": "cat",
                    "PSQL_PAGER": "cat",
                    "PGCONNECT_TIMEOUT": "5",
                },
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"command failed: {args[:2]}: "
                    f"{completed.stderr[-1500:]}"
                )
            return completed.stdout.strip()

        sql = r"""
        SET statement_timeout = '5s';
        SET lock_timeout = '500ms';
        SET default_transaction_read_only = on;
        BEGIN READ ONLY;
        SELECT jsonb_build_object(
          'captured_at', clock_timestamp(),
          'transaction_read_only',
            current_setting('transaction_read_only')::boolean,
          'identity', jsonb_build_object(
            'cluster_name', current_setting('cluster_name'),
            'server_version', current_setting('server_version'),
            'server_version_num',
              current_setting('server_version_num')::integer,
            'server_address', inet_server_addr()::text,
            'server_port', inet_server_port(),
            'in_recovery', pg_is_in_recovery(),
            'postmaster_started_at', pg_postmaster_start_time(),
            'config_loaded_at', pg_conf_load_time()
          ),
          'control', (
            SELECT jsonb_build_object(
              'system_identifier', s.system_identifier,
              'pg_control_version', s.pg_control_version,
              'catalog_version_no', s.catalog_version_no,
              'timeline_id', c.timeline_id,
              'checkpoint_lsn', c.checkpoint_lsn,
              'redo_lsn', c.redo_lsn,
              'checkpoint_time', c.checkpoint_time
            )
            FROM pg_control_system() AS s
            CROSS JOIN pg_control_checkpoint() AS c
          ),
          'settings', (
            SELECT jsonb_object_agg(name, setting ORDER BY name)
            FROM pg_settings
            WHERE name = ANY (ARRAY[
              'archive_mode','data_checksums','hot_standby',
              'max_connections','max_slot_wal_keep_size',
              'synchronous_standby_names','wal_level'
            ])
          ),
          'activity', (
            SELECT coalesce(
              jsonb_agg(to_jsonb(q) ORDER BY state, wait_event_type),
              '[]'::jsonb
            )
            FROM (
              SELECT
                coalesce(state, 'none') AS state,
                coalesce(wait_event_type, 'none') AS wait_event_type,
                count(*) AS sessions,
                round(
                  max(extract(epoch FROM
                    (clock_timestamp() - xact_start)))
                    FILTER (WHERE xact_start IS NOT NULL)::numeric,
                  3
                ) AS max_xact_seconds
              FROM pg_stat_activity
              WHERE backend_type = 'client backend'
              GROUP BY state, wait_event_type
            ) AS q
          ),
          'locks', (
            SELECT jsonb_build_object(
              'total', count(*),
              'not_granted', count(*) FILTER (WHERE NOT granted)
            )
            FROM pg_locks
          ),
          'replication', (
            SELECT coalesce(
              jsonb_agg(to_jsonb(q) ORDER BY state, sync_state),
              '[]'::jsonb
            )
            FROM (
              SELECT
                state,
                sync_state,
                count(*) AS streams,
                max(
                  pg_wal_lsn_diff(sent_lsn, replay_lsn)
                )::bigint AS max_sent_replay_gap_bytes
              FROM pg_stat_replication
              GROUP BY state, sync_state
            ) AS q
          ),
          'slots', (
            SELECT coalesce(
              jsonb_agg(to_jsonb(q) ORDER BY slot_type, active),
              '[]'::jsonb
            )
            FROM (
              SELECT
                slot_type,
                active,
                count(*) AS slots,
                max(
                  pg_wal_lsn_diff(
                    pg_current_wal_lsn(), restart_lsn
                  )
                )::bigint AS max_retained_bytes
              FROM pg_replication_slots
              GROUP BY slot_type, active
            ) AS q
          ),
          'archiver', (
            SELECT jsonb_build_object(
              'archived_count', archived_count,
              'failed_count', failed_count,
              'last_archived_time', last_archived_time,
              'last_failed_time', last_failed_time,
              'stats_reset', stats_reset
            )
            FROM pg_stat_archiver
          ),
          'database_stats', (
            SELECT jsonb_build_object(
              'database_count', count(*),
              'commits', coalesce(sum(xact_commit), 0)::bigint,
              'rollbacks', coalesce(sum(xact_rollback), 0)::bigint,
              'deadlocks', coalesce(sum(deadlocks), 0)::bigint,
              'stats_reset_min', min(stats_reset),
              'stats_reset_max', max(stats_reset)
            )
            FROM pg_stat_database
          )
        );
        COMMIT;
        """

        output = command(
            [
                "psql",
                "-X",
                "-w",
                "-q",
                "-A",
                "-t",
                "--no-psqlrc",
                "-v",
                "ON_ERROR_STOP=1",
                "-d",
                f"service={service} dbname=postgres "
                "application_name=pg36-ch31-capture",
                "-c",
                sql,
            ]
        )
        rows = [
            line for line in output.splitlines()
            if line.lstrip().startswith("{")
        ]
        if len(rows) != 1:
            raise RuntimeError("PostgreSQL snapshot was not one JSON row")
        postgres = json.loads(rows[0])
        if postgres["identity"]["cluster_name"] != expected_cluster:
            raise RuntimeError("connected PostgreSQL cluster is not declared")

        patroni = []
        for address in members:
            with urllib.request.urlopen(
                f"http://{address}:8008/patroni", timeout=5
            ) as response:
                value = json.load(response)
            patroni.append(
                {
                    "address": address,
                    "state": value.get("state"),
                    "role": value.get("role"),
                    "server_version": value.get("server_version"),
                    "timeline": value.get("timeline"),
                    "pending_restart": bool(
                        value.get("pending_restart", False)
                    ),
                }
            )

        backrest_raw = json.loads(
            command(
                [
                    "sudo",
                    "-n",
                    "-u",
                    "postgres",
                    "pgbackrest",
                    f"--stanza={stanza}",
                    "info",
                    "--output=json",
                ],
                timeout=30,
            )
        )
        if len(backrest_raw) != 1:
            raise RuntimeError("pgBackRest stanza result is not unique")
        stanza_value = backrest_raw[0]
        backups = stanza_value.get("backup", [])
        latest = (
            max(
                backups,
                key=lambda row: row.get("timestamp", {}).get("stop", 0),
            )
            if backups
            else None
        )
        databases = stanza_value.get("db", [])
        database = databases[-1] if databases else {}
        archives = stanza_value.get("archive", [])
        archive = archives[-1] if archives else {}
        backrest = {
            "name": stanza_value.get("name"),
            "status_code": stanza_value.get("status", {}).get("code"),
            "backup_count": len(backups),
            "latest_backup": (
                {
                    "label": latest.get("label"),
                    "type": latest.get("type"),
                    "started_at_epoch":
                        latest.get("timestamp", {}).get("start"),
                    "stopped_at_epoch":
                        latest.get("timestamp", {}).get("stop"),
                    "start_lsn": latest.get("lsn", {}).get("start"),
                    "stop_lsn": latest.get("lsn", {}).get("stop"),
                    "error": latest.get("error"),
                }
                if latest
                else None
            ),
            "database": {
                "system_identifier": database.get("system-id"),
                "version": database.get("version"),
            },
            "archive": {
                "id": archive.get("id"),
                "min": archive.get("min"),
                "max": archive.get("max"),
            },
        }

        ntp = None
        try:
            ntp = command(
                [
                    "timedatectl",
                    "show",
                    "--property=NTPSynchronized",
                    "--value",
                ],
                timeout=5,
            )
        except Exception:
            ntp = "unavailable"
        clocksource_path = Path(
            "/sys/devices/system/clocksource/clocksource0/"
            "current_clocksource"
        )
        clocksource = (
            clocksource_path.read_text(encoding="utf-8").strip()
            if clocksource_path.is_file()
            else "unavailable"
        )
        print(
            json.dumps(
                {
                    "captured_at":
                        datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    "host": {
                        "hostname": platform.node(),
                        "architecture": platform.machine(),
                        "clocksource": clocksource,
                        "ntp_synchronized": ntp,
                    },
                    "postgresql": postgres,
                    "patroni": patroni,
                    "pgbackrest": backrest,
                    "collection": {
                        "sql_transaction": "READ ONLY",
                        "raw_query_text": False,
                        "raw_log_export": False,
                        "configuration_content": False,
                        "mutation": "none",
                    },
                },
                sort_keys=True,
            )
        )
        '''
    )
    completed = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            f"{ssh_user}@{bastion}",
            "python3",
            "-",
            str(target["service"]),
            str(target["cluster"]),
            ",".join(target["patroni_members"]),
            str(target["pgbackrest_stanza"]),
        ],
        input=script,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
    )
    if completed.returncode != 0:
        raise CaptureError(
            f"remote read-only capture failed: "
            f"{completed.stderr[-3000:]}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CaptureError(
            "remote capture was not JSON: "
            f"{completed.stdout[-2000:]}"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements = read_json(args.source_dir / "requirements.json")
    target = requirements["target"]
    if args.bastion != target["bastion"]:
        raise CaptureError("bastion differs from declared sandbox")
    if args.ssh_user != target["ssh_user"]:
        raise CaptureError("SSH user differs from declared sandbox")

    evidence = {
        "schema": "pg36-ch31-preflight-evidence-v1",
        "run_id": str(uuid.uuid4()),
        "captured_at": utc_now(),
        "target_id": target["id"],
        "source_hashes": source_hashes(args.source_dir),
        "upstream_hashes": upstream_hashes(
            args.source_dir,
            args.upstream_root,
            requirements,
        ),
        "live": remote_capture(
            ssh_user=args.ssh_user,
            bastion=args.bastion,
            target=target,
        ),
        "claims": {
            "database_mutated": False,
            "patroni_paused": False,
            "failover_executed": False,
            "service_restarted": False,
            "connection_terminated": False,
            "route_changed": False,
            "backup_restored": False,
            "production_incident_resolved": False,
        },
        "production_ch31_gate": "pending",
    }
    write_private_json(args.output, evidence)
    print(
        json.dumps(
            {
                "run_id": evidence["run_id"],
                "target": evidence["target_id"],
                "cluster": evidence["live"]["postgresql"]
                ["identity"]["cluster_name"],
                "mutation": "none",
                "status": "capture-ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
