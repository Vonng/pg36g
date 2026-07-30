#!/usr/bin/env python3
"""Capture a secret-free chapter 22 service-layer snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from common import (
    LabError,
    patroni_list,
    pgbouncer_config,
    project_pgbouncer_config,
    read_json,
    remote_json_psql,
    ssh_command,
    utc_now,
    write_json,
)


HAPROXY_PROJECTION = r"""
import json
import pathlib
import re
import shlex
import subprocess

files = {
    "primary": pathlib.Path("/etc/haproxy/pg-test-primary.cfg"),
    "replica": pathlib.Path("/etc/haproxy/pg-test-replica.cfg"),
    "default": pathlib.Path("/etc/haproxy/pg-test-default.cfg"),
    "offline": pathlib.Path("/etc/haproxy/pg-test-offline.cfg"),
}
services = {}
for name, path in files.items():
    text = path.read_text(encoding="utf-8")
    service = {
        "port": None,
        "mode": None,
        "maxconn": None,
        "health_path": None,
        "expected_status": None,
        "default_server": {},
        "servers": [],
    }
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = shlex.split(line)
        if fields[0] == "bind":
            service["port"] = int(fields[1].rsplit(":", 1)[1])
        elif fields[0] == "mode":
            service["mode"] = fields[1]
        elif fields[0] == "maxconn":
            service["maxconn"] = int(fields[1])
        elif fields[:5] == ["http-check", "send", "meth", "OPTIONS", "uri"]:
            service["health_path"] = fields[5]
        elif fields[:3] == ["http-check", "expect", "status"]:
            service["expected_status"] = int(fields[3])
        elif fields[0] == "default-server":
            values = {}
            flag_names = {"on-marked-down", "shutdown-sessions"}
            i = 1
            while i < len(fields):
                key = fields[i]
                if key == "on-marked-down" and i + 1 < len(fields):
                    values["on_marked_down"] = fields[i + 1]
                    i += 2
                elif key in flag_names:
                    values[key.replace("-", "_")] = True
                    i += 1
                elif i + 1 < len(fields):
                    value = fields[i + 1]
                    if key in {"rise", "fall", "maxconn", "maxqueue", "weight"}:
                        value = int(value)
                    values[key.replace("-", "_")] = value
                    i += 2
                else:
                    values[key.replace("-", "_")] = True
                    i += 1
            service["default_server"] = values
        elif fields[0] == "server":
            address, destination_port = fields[2].rsplit(":", 1)
            check_port = fields[fields.index("port") + 1]
            service["servers"].append(
                {
                    "member": fields[1],
                    "address": address,
                    "destination_port": int(destination_port),
                    "check_port": int(check_port),
                    "backup": "backup" in fields,
                }
            )
    services[name] = service

packages = {}
for package in ("haproxy", "pgbouncer", "postgresql-18"):
    packages[package] = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", package],
        text=True,
    ).strip()

ports = set()
for line in subprocess.check_output(["ss", "-ltnH"], text=True).splitlines():
    fields = line.split()
    if len(fields) < 4:
        continue
    match = re.search(r":([0-9]+)$", fields[3])
    if match:
        ports.add(int(match.group(1)))

print(
    json.dumps(
        {
            "schema": "pg36-ch22-entry-projection-v1",
            "services": services,
            "package_versions": packages,
            "tcp_listener_ports": sorted(ports),
        },
        sort_keys=True,
    )
)
"""


POSTGRES_STATE_SQL = r"""
SELECT json_build_object(
  'schema', 'pg36-ch22-postgresql-state-v1',
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'server_port', current_setting('port')::int,
  'cluster_name', current_setting('cluster_name'),
  'postmaster_started_at',
      to_char(pg_postmaster_start_time() AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only',
      current_setting('transaction_read_only')::boolean,
  'active_backends', (
      SELECT count(*)
        FROM pg_stat_activity
       WHERE backend_type = 'client backend'
  ),
  'settings', (
      SELECT json_object_agg(name, value)
        FROM (
          SELECT name,
                 CASE
                   WHEN name IN (
                     'max_connections',
                     'superuser_reserved_connections',
                     'reserved_connections',
                     'max_locks_per_transaction'
                   ) THEN to_jsonb(setting::bigint)
                   WHEN name IN (
                     'idle_in_transaction_session_timeout',
                     'statement_timeout'
                   ) THEN to_jsonb(setting::bigint)
                   ELSE to_jsonb(setting)
                 END AS value
            FROM pg_settings
           WHERE name IN (
             'max_connections',
             'superuser_reserved_connections',
             'reserved_connections',
             'idle_in_transaction_session_timeout',
             'statement_timeout',
             'max_locks_per_transaction',
             'work_mem',
             'temp_buffers'
           )
        ) AS selected
  )
);
"""


def capture_entry_projection(user: str, host: str) -> dict[str, Any]:
    result = ssh_command(
        user,
        host,
        ["sudo", "-n", "python3", "-"],
        stdin=HAPROXY_PROJECTION,
        timeout=30,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LabError(f"entry projection returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LabError("entry projection is not an object")
    return value


def capture_postgres(user: str, host: str) -> dict[str, Any]:
    value = remote_json_psql(
        user,
        host,
        "postgres",
        POSTGRES_STATE_SQL,
    )
    if not isinstance(value, dict):
        raise LabError(f"PostgreSQL state on {host} is not an object")
    value["member_address"] = host
    return value


def capture_snapshot(
    requirements: dict[str, Any],
    user: str,
    phase: str,
) -> dict[str, Any]:
    target = requirements["target"]
    members = target["members"]
    hosts = [str(members[name]) for name in sorted(members)]
    observer = str(members["pg-test-3"])
    entry = str(target["entry_address"])
    return {
        "schema": "pg36-ch22-service-snapshot-v1",
        "release": requirements["release"],
        "phase": phase,
        "captured_at": utc_now(milliseconds=True),
        "target": target["id"],
        "topology": patroni_list(user, observer),
        "entry": capture_entry_projection(user, entry),
        "postgres": {
            host: capture_postgres(user, host)
            for host in hosts
        },
        "pgbouncer": {
            host: project_pgbouncer_config(
                pgbouncer_config(user, host)
            )
            for host in hosts
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", default="current")
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        if not re.fullmatch(r"[a-z0-9-]+", args.phase):
            raise LabError("phase name is not safe")
        snapshot = capture_snapshot(
            requirements,
            args.ssh_user,
            args.phase,
        )
        write_json(args.output, snapshot)
    except (LabError, KeyError, TypeError, OSError) as exc:
        sys.stderr.write(f"service capture failed: {exc}\n")
        return 1
    print(f"status=captured phase={args.phase}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
