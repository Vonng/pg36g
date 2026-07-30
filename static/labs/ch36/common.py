#!/usr/bin/env python3
"""Shared helpers for the chapter 36 offline postmortem compiler."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Raised when an input or generated artifact violates the lab contract."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ContractError(f"JSON Pointer must start with '/': {pointer!r}")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise ContractError(f"JSON Pointer list token does not resolve: {pointer!r}") from exc
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ContractError(f"JSON Pointer does not resolve: {pointer!r}")
    return current


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def phase_for_due_day(due_day: int) -> str:
    if 1 <= due_day <= 30:
        return "day-0-30"
    if 31 <= due_day <= 60:
        return "day-31-60"
    if 61 <= due_day <= 90:
        return "day-61-90"
    raise ContractError(f"due day must be within 1..90, got {due_day!r}")
