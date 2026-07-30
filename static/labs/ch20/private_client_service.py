#!/usr/bin/env python3
"""Create a mode-0600 libpq service file without printing its secret."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


class ServiceError(RuntimeError):
    pass


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
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError(f"cannot read requirements: {exc}") from exc
    if not isinstance(value, dict):
        raise ServiceError("requirements must be an object")
    return value


def find_user(inventory: dict[str, Any], cluster: str, username: str) -> str:
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
    raise ServiceError("declared sandbox client credential was not found")


def main() -> int:
    args = parse_args()
    try:
        source_mode = stat.S_IMODE(args.inventory.stat().st_mode)
        if source_mode != 0o600:
            raise ServiceError("private inventory mode must be 0600")
        inventory = read_yaml(args.inventory)
        requirements = read_json(args.requirements)
        target = requirements["target"]
        probe = requirements["client_probe"]
        password = find_user(
            inventory,
            str(target["cluster"]),
            str(probe["user"]),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(
            [
                "[pg36-ch20]",
                f"host={probe['service_host']}",
                f"port={probe['service_port']}",
                f"dbname={probe['database']}",
                f"user={probe['user']}",
                f"password={password}",
                f"sslmode={probe['sslmode']}",
                "connect_timeout=2",
                f"target_session_attrs={probe['target_session_attrs']}",
                "application_name=pg36-ch20-client-probe",
                "",
            ]
        )
        descriptor = os.open(
            args.output,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        if stat.S_IMODE(args.output.stat().st_mode) != 0o600:
            raise ServiceError("generated service file mode drifted")
    except (ServiceError, KeyError, TypeError, OSError) as error:
        sys.stderr.write(f"service file generation failed: {error}\n")
        return 1
    print("status=private-service-created")
    print("service=pg36-ch20")
    print("secret_values_exported=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
