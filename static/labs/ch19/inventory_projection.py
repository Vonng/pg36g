#!/usr/bin/env python3
"""Project a Pigsty inventory into a deliberately secret-free evidence file."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


SECRET_KEY = re.compile(
    r"(password|passwd|secret|credential|private_key|access_key|token)",
    re.IGNORECASE,
)

SAFE_GLOBAL_FIELDS = (
    "version",
    "admin_ip",
    "region",
    "node_tune",
    "pg_conf",
    "pg_version",
    "pg_encoding",
    "pg_locale",
    "pg_checksum",
    "pgbackrest_method",
    "node_firewall_mode",
)

SAFE_HOST_FIELDS = (
    "infra_seq",
    "etcd_seq",
    "minio_seq",
    "pg_seq",
    "pg_role",
    "pg_offline_query",
)


class ProjectionError(RuntimeError):
    pass


def count_secret_fields(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            (1 if SECRET_KEY.search(str(key)) else 0)
            + count_secret_fields(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return sum(count_secret_fields(child) for child in value)
    return 0


def safe_host_map(hosts: Any) -> dict[str, dict[str, Any]]:
    if hosts is None:
        return {}
    if not isinstance(hosts, dict):
        raise ProjectionError("group hosts must be a mapping")
    result: dict[str, dict[str, Any]] = {}
    for address, host_vars in sorted(hosts.items()):
        if host_vars is None:
            host_vars = {}
        if not isinstance(host_vars, dict):
            raise ProjectionError(f"host variables for {address} must be a mapping")
        result[str(address)] = {
            key: host_vars[key]
            for key in SAFE_HOST_FIELDS
            if key in host_vars
        }
    return result


def project(source: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ProjectionError(f"cannot parse inventory: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("all"), dict):
        raise ProjectionError("inventory needs an all mapping")

    all_group = document["all"]
    global_vars = all_group.get("vars") or {}
    children = all_group.get("children") or {}
    if not isinstance(global_vars, dict) or not isinstance(children, dict):
        raise ProjectionError("inventory all.vars/all.children must be mappings")

    groups: dict[str, Any] = {}
    clusters: dict[str, Any] = {}
    all_hosts: set[str] = set()
    for group_name, group in sorted(children.items()):
        if not isinstance(group, dict):
            continue
        hosts = safe_host_map(group.get("hosts"))
        all_hosts.update(hosts)
        group_vars = group.get("vars") or {}
        if not isinstance(group_vars, dict):
            raise ProjectionError(f"group variables for {group_name} must be a mapping")
        groups[str(group_name)] = {
            "hosts": hosts,
            "host_count": len(hosts),
        }
        cluster_name = group_vars.get("pg_cluster")
        if isinstance(cluster_name, str) and cluster_name:
            databases = group_vars.get("pg_databases") or []
            clusters[cluster_name] = {
                "group": str(group_name),
                "hosts": hosts,
                "database_count": len(databases) if isinstance(databases, list) else 0,
                "user_count": len(group_vars.get("pg_users") or [])
                if isinstance(group_vars.get("pg_users") or [], list)
                else 0,
            }

    source_mode = stat.S_IMODE(source.stat().st_mode)
    return {
        "schema": "pg36-ch19-inventory-projection-v1",
        "status": "secret-free-projection",
        "source": {
            "mode_octal": f"{source_mode:04o}",
            "content_fingerprint": "withheld-secret-bearing-source",
            "secret_fields_redacted": count_secret_fields(document),
            "secret_values_exported": 0,
        },
        "global": {
            field: global_vars[field]
            for field in SAFE_GLOBAL_FIELDS
            if field in global_vars
        },
        "host_count": len(all_hosts),
        "hosts": sorted(all_hosts),
        "groups": groups,
        "postgresql_clusters": clusters,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = project(args.inventory)
    except ProjectionError as error:
        sys.stderr.write(f"projection failed: {error}\n")
        return 1
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
