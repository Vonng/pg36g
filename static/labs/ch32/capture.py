#!/usr/bin/env python3
"""Capture a read-only readiness snapshot for the chapter 32 PITR lab."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from common import (
    LabError,
    patroni_list,
    pgbackrest_info,
    read_json,
    remote_json_psql,
    require_stable_source,
    sanitized_repo_info,
    source_hashes,
    source_sql_state,
    ssh_command,
    upstream_hashes,
    utc_now,
    write_json,
)


class CaptureError(LabError):
    """Raised when the declared sandbox is not ready."""


def restore_host_probe(
    user: str,
    host: str,
    root_prefix: str,
    port: int,
) -> dict[str, Any]:
    script = r"""
set -Eeuo pipefail
prefix="$1"
port="$2"
case "$prefix" in
  /data/pg36-ch32-restore) ;;
  *) printf 'unexpected restore prefix\n' >&2; exit 64 ;;
esac
prefix_symlink=false
[[ -L "$prefix" ]] && prefix_symlink=true
candidate_count=0
if [[ -d "$prefix" ]]; then
  candidate_count=$(find "$prefix" -mindepth 1 -maxdepth 1 -print | wc -l)
fi
tcp_listener=false
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  tcp_listener=true
fi
printf '{"candidate_count":%s,"prefix_symlink":%s,"tcp_listener":%s}\n' \
  "$candidate_count" "$prefix_symlink" "$tcp_listener"
"""
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "bash",
            "-s",
            "--",
            root_prefix,
            str(port),
        ],
        stdin=script,
        timeout=15,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CaptureError("restore-host probe returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise CaptureError("restore-host probe is not an object")
    return value


def toolchain_probe(user: str, host: str) -> dict[str, Any]:
    commands = {
        "pig": ["pig", "version"],
        "pgbackrest": [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "pgbackrest",
            "version",
        ],
        "postgres": [
            "/usr/lib/postgresql/18/bin/postgres",
            "--version",
        ],
    }
    result: dict[str, Any] = {}
    for label, command in commands.items():
        completed = ssh_command(
            user,
            host,
            command,
            timeout=15,
        )
        result[label] = completed.stdout.strip()
    help_text = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "pig",
            "pitr",
            "--help",
        ],
        timeout=20,
    ).stdout
    required_tokens = (
        "--xid",
        "--exclusive",
        "--target-action",
        "--target-timeline",
        "--set",
        "--data",
        "--no-restart",
        "--plan",
        "--yes",
    )
    result["pig_pitr_required_flags"] = {
        token: token in help_text for token in required_tokens
    }
    result["pig_pitr_all_required_flags"] = all(
        result["pig_pitr_required_flags"].values()
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        target = requirements["target"]
        fixture = requirements["fixture"]
        restore = requirements["restore"]
        source_host = str(target["source_address"])
        restore_host = str(target["restore_address"])
        database = str(fixture["database"])
        schema = str(fixture["schema"])

        topology = patroni_list(args.ssh_user, source_host)
        require_stable_source(topology, requirements)
        source, source_system_id = source_sql_state(
            args.ssh_user,
            source_host,
            database,
            schema,
        )
        if (
            source.get("cluster_name") != target["cluster"]
            or source.get("in_recovery") is not False
            or source.get("fixture_schema_exists") is not False
            or source.get("server_version_num", 0) // 10000
            != target["postgresql_major"]
        ):
            raise CaptureError("source PostgreSQL preflight failed")

        restore_member = remote_json_psql(
            args.ssh_user,
            restore_host,
            database,
            r"""
SELECT json_build_object(
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only',
      current_setting('transaction_read_only')::boolean,
  'replay_lsn', pg_last_wal_replay_lsn()::text,
  'fixture_schema_exists',
      to_regnamespace('pg36_ch32') IS NOT NULL,
  'system_identifier', system_identifier::text
)
FROM pg_control_system();
""",
        )
        if (
            not isinstance(restore_member, dict)
            or restore_member.get("cluster_name") != target["cluster"]
            or restore_member.get("in_recovery") is not True
            or restore_member.get("fixture_schema_exists") is not False
            or restore_member.pop("system_identifier", None)
            != source_system_id
        ):
            raise CaptureError("restore host is not the declared live replica")

        host_probe = restore_host_probe(
            args.ssh_user,
            restore_host,
            str(restore["root_prefix"]),
            int(restore["port"]),
        )
        if (
            host_probe.get("candidate_count") != 0
            or host_probe.get("prefix_symlink") is not False
            or host_probe.get("tcp_listener") is not False
        ):
            raise CaptureError("restore host has an unsafe stale candidate")

        toolchain = toolchain_probe(args.ssh_user, restore_host)
        if toolchain.get("pig_pitr_all_required_flags") is not True:
            raise CaptureError("installed pig pitr lacks required flags")

        repository = pgbackrest_info(
            args.ssh_user,
            source_host,
            str(requirements["repository"]["stanza"]),
        )
        write_json(
            args.output,
            {
                "schema": "pg36-ch32-preflight-v1",
                "run_id": str(uuid.uuid4()),
                "captured_at": utc_now(),
                "target": target["id"],
                "mutation": "none",
                "source_sha256": source_hashes(args.source_dir),
                "upstream_sha256": upstream_hashes(
                    args.source_dir,
                    requirements,
                ),
                "topology": topology,
                "source": source,
                "source_system_identifier_recorded": False,
                "restore_member": restore_member,
                "restore_host": host_probe,
                "repository": sanitized_repo_info(repository),
                "toolchain": toolchain,
                "claims": {
                    "patroni_changed": False,
                    "dcs_changed": False,
                    "route_changed": False,
                    "database_mutated": False,
                    "backup_created": False,
                    "restore_started": False,
                    "process_terminated": False,
                },
                "decision": {
                    "sandbox_ready": True,
                    "recoverability": "not-proven-by-capture",
                    "production_ch32_gate": "pending",
                },
            },
        )
    except (LabError, KeyError, TypeError, OSError) as exc:
        sys.stderr.write(f"capture failed: {exc}\n")
        return 1

    print("status=capture-ok")
    print("mutation=none")
    print("production_ch32_gate=pending")
    print(f"evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
