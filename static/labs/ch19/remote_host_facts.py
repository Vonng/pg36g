#!/usr/bin/env python3
"""Read-only Linux host fact collector executed through SSH."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SERVICES = (
    "etcd",
    "haproxy",
    "minio",
    "nginx",
    "patroni",
    "pgbouncer",
    "vector",
    "victoria-metrics",
    "victoria-logs",
)

PACKAGES = (
    "etcd",
    "haproxy",
    "minio",
    "patroni",
    "pgbackrest",
    "pgbouncer",
    "postgresql-18",
    "postgresql-client-18",
)


def command(*args: str) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in read("/etc/os-release").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.lower()] = value.strip().strip('"')
    return result


def meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in read("/proc/meminfo").splitlines():
        match = re.match(r"^([^:]+):\s+(\d+)\s+kB$", line)
        if match:
            result[match.group(1)] = int(match.group(2)) * 1024
    return result


def current_bracket_value(path: str) -> str:
    match = re.search(r"\[([^\]]+)\]", read(path))
    return match.group(1) if match else ""


def integer_file(path: str) -> int | None:
    value = read(path)
    try:
        return int(value)
    except ValueError:
        return None


def mount_fact(target: str) -> dict[str, Any]:
    raw = command(
        "findmnt",
        "--json",
        "--output",
        "TARGET,SOURCE,FSTYPE,OPTIONS,SIZE,AVAIL",
        "--target",
        target,
    )
    if not raw:
        return {}
    try:
        rows = json.loads(raw).get("filesystems", [])
    except (json.JSONDecodeError, AttributeError):
        return {}
    if not rows:
        return {}
    row = rows[0]
    return {
        "target": row.get("target"),
        "source": row.get("source"),
        "fstype": row.get("fstype"),
        "options": sorted(str(row.get("options", "")).split(",")),
        "size": row.get("size"),
        "available": row.get("avail"),
    }


def service_states() -> dict[str, str]:
    result: dict[str, str] = {}
    for service in SERVICES:
        state = command("systemctl", "is-active", service)
        result[service] = state or "inactive"
    return result


def package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in PACKAGES:
        version = command(
            "dpkg-query",
            "--show",
            "--showformat=${Version}",
            package,
        )
        if version:
            result[package] = version
    return result


def listening_ports() -> list[int]:
    raw = command("ss", "--listening", "--tcp", "--numeric", "--no-header")
    ports: set[int] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        match = re.search(r":(\d+)$", fields[3])
        if match:
            ports.add(int(match.group(1)))
    return sorted(ports)


def machine_identity() -> str:
    identity = read("/etc/machine-id")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest() if identity else ""


def num_numa_nodes() -> int:
    return len(list(Path("/sys/devices/system/node").glob("node[0-9]*")))


def firewall_fact() -> dict[str, Any]:
    return {
        "ufw_service": command("systemctl", "is-active", "ufw") or "inactive",
        "firewalld_service": command("systemctl", "is-active", "firewalld")
        or "inactive",
        "nftables_service": command("systemctl", "is-active", "nftables")
        or "inactive",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-ip", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    memory = meminfo()
    root_usage = shutil.disk_usage("/")
    # `/pg` is normally a symlink into a PostgreSQL-owned mode-0700 data
    # directory.  Following it as the unprivileged SSH evidence user would
    # turn a harmless fact collection into PermissionError.  `/data` is the
    # stable Pigsty storage root and identifies the same backing filesystem
    # without crossing the database directory's permission boundary.
    pg_path = "/data" if os.path.lexists("/data") else "/"
    result = {
        "schema": "pg36-ch19-host-facts-v1",
        "target_ip": args.target_ip,
        "hostname": platform.node(),
        "machine_id_sha256": machine_identity(),
        "kernel": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "virtualization": command("systemd-detect-virt") or "none",
        "os": os_release(),
        "cpu": {
            "logical_count": os.cpu_count(),
            "model": command(
                "sh",
                "-c",
                "awk -F: '/model name|Model/{print $2; exit}' /proc/cpuinfo",
            ).strip(),
            "numa_nodes": num_numa_nodes(),
        },
        "memory": {
            "total_bytes": memory.get("MemTotal", 0),
            "swap_total_bytes": memory.get("SwapTotal", 0),
            "hugepages_total": integer_file("/proc/sys/vm/nr_hugepages"),
            "hugepage_size_bytes": memory.get("Hugepagesize", 0),
            "transparent_hugepage_enabled": current_bracket_value(
                "/sys/kernel/mm/transparent_hugepage/enabled"
            ),
            "transparent_hugepage_defrag": current_bracket_value(
                "/sys/kernel/mm/transparent_hugepage/defrag"
            ),
            "overcommit_memory": integer_file("/proc/sys/vm/overcommit_memory"),
            "swappiness": integer_file("/proc/sys/vm/swappiness"),
        },
        "storage": {
            "root_total_bytes": root_usage.total,
            "root_free_bytes": root_usage.free,
            "root_mount": mount_fact("/"),
            "pg_mount": mount_fact(pg_path),
        },
        "clock": {
            "timezone": command("timedatectl", "show", "--property=Timezone", "--value"),
            "ntp_synchronized": command(
                "timedatectl",
                "show",
                "--property=NTPSynchronized",
                "--value",
            )
            == "yes",
        },
        "network": {
            "addresses": command("hostname", "-I").split(),
            "resolv_conf_nameservers": [
                line.split()[1]
                for line in read("/etc/resolv.conf").splitlines()
                if line.startswith("nameserver ") and len(line.split()) >= 2
            ],
            "listening_tcp_ports": listening_ports(),
            "firewall": firewall_fact(),
        },
        "services": service_states(),
        "packages": package_versions(),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
