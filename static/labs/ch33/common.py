#!/usr/bin/env python3
"""Shared, secret-free helpers for the chapter 33 lab."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LabError(RuntimeError):
    """Raised when a guarded lab operation cannot be proved safe."""


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: float = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabError(f"cannot execute {args[0]}: {exc}") from exc
    if check and result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        detail = lines[-1] if lines else f"exit {result.returncode}"
        raise LabError(f"command failed ({args[0]}): {detail}")
    return result


def ssh_base(user: str, host: str) -> list[str]:
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "LogLevel=ERROR",
        f"{user}@{host}",
    ]


def service_env(service_file: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGSERVICEFILE"] = str(service_file)
    environment["PGSERVICE"] = "pg36-ch33"
    return environment
