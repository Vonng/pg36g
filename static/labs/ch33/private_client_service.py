#!/usr/bin/env python3
"""Create a mode-0600 libpq service file without exporting its secret."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


class ServiceError(RuntimeError):
    """Raised when the private inventory does not match the lab contract."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ServiceError(f"cannot read private inventory: {exc}") from exc
    if not isinstance(value, dict):
        raise ServiceError("private inventory must be a mapping")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError(f"cannot read requirements: {exc}") from exc
    if not isinstance(value, dict):
        raise ServiceError("requirements must be an object")
    return value


def find_password(
    inventory: dict[str, Any],
    cluster: str,
    username: str,
) -> str:
    try:
        groups = inventory["all"]["children"]
    except (KeyError, TypeError) as exc:
        raise ServiceError(f"inventory hierarchy drifted: {exc}") from exc
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        variables = group.get("vars") or {}
        if variables.get("pg_cluster") != cluster:
            continue
        for user in variables.get("pg_users") or []:
            if isinstance(user, dict) and user.get("name") == username:
                password = user.get("password")
                if isinstance(password, str) and password:
                    return password
    raise ServiceError("sandbox client credential was not found")


def verify_output(path: Path, probe: dict[str, Any]) -> None:
    if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.is_symlink():
        raise ServiceError("generated service file is not a regular mode-0600 file")
    parser = configparser.ConfigParser(interpolation=None)
    with path.open(encoding="utf-8") as stream:
        parser.read_file(stream)
    section = parser["pg36-ch33"]
    expected = {
        "host": str(probe["service_host"]),
        "port": str(probe["service_port"]),
        "dbname": str(probe["database"]),
        "user": str(probe["user"]),
        "sslmode": str(probe["sslmode"]),
        "target_session_attrs": str(probe["target_session_attrs"]),
    }
    if any(section.get(key) != value for key, value in expected.items()):
        raise ServiceError("generated endpoint drifted from requirements")
    if not section.get("password"):
        raise ServiceError("generated credential is empty")


def main() -> int:
    args = parse_args()
    try:
        if (
            not args.inventory.is_file()
            or args.inventory.is_symlink()
            or stat.S_IMODE(args.inventory.stat().st_mode) != 0o600
        ):
            raise ServiceError(
                "private inventory must be a regular mode-0600 file"
            )
        requirements = read_json(args.requirements)
        probe = requirements["client_probe"]
        target = requirements["target"]
        password = find_password(
            read_yaml(args.inventory),
            str(target["cluster"]),
            str(probe["user"]),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            args.output,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        payload = "\n".join(
            [
                "[pg36-ch33]",
                f"host={probe['service_host']}",
                f"port={probe['service_port']}",
                f"dbname={probe['database']}",
                f"user={probe['user']}",
                f"password={password}",
                f"sslmode={probe['sslmode']}",
                "connect_timeout=2",
                f"target_session_attrs={probe['target_session_attrs']}",
                "application_name=pg36-ch33-client-probe",
                "",
            ]
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        verify_output(args.output, probe)
    except (
        ServiceError,
        KeyError,
        TypeError,
        OSError,
        configparser.Error,
    ) as exc:
        print(f"service generation failed: {exc}", file=sys.stderr)
        return 1
    print("status=private-service-created")
    print("service=pg36-ch33")
    print("secret_values_exported=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
