#!/usr/bin/env python3
"""Review chapter 26 private evidence for integrity, privacy, and claim scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


class ReviewFailure(RuntimeError):
    pass


SECRET_PATTERNS = [
    re.compile(rb"postgres(?:ql)?://[^\s:/]+:[^@\s]+@", re.IGNORECASE),
    re.compile(rb"(?:password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(rb"PGPASSWORD\s*=", re.IGNORECASE),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"aws_secret_access_key", re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def review_modes(root: Path) -> tuple[int, int]:
    directories = 0
    files = 0
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            raise ReviewFailure(f"evidence symlink is forbidden: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            directories += 1
            if mode & 0o077:
                raise ReviewFailure(f"evidence directory is not private: {path} {mode:o}")
        elif path.is_file():
            files += 1
            if mode & 0o077:
                raise ReviewFailure(f"evidence file is not private: {path} {mode:o}")
    return directories, files


def review_secrets(root: Path) -> int:
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        scanned += len(data)
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                raise ReviewFailure(
                    f"possible secret material matched {pattern.pattern!r} in {path}"
                )
    return scanned


def review_raw_manifest(evidence_dir: Path, capacity: dict[str, Any]) -> tuple[int, int]:
    run_count = 0
    raw_files = 0
    remote = evidence_dir / "remote"
    for run in capacity["experiment"]["runs"]:
        run_count += 1
        run_dir = remote / "runs" / run["run_id"]
        if not run_dir.is_dir():
            raise ReviewFailure(f"raw run directory is missing: {run_dir}")
        for name, expected in run["raw_files"].items():
            path = run_dir / name
            if not path.is_file():
                raise ReviewFailure(f"raw file is missing: {path}")
            if path.stat().st_size != expected["bytes"]:
                raise ReviewFailure(f"raw file size drifted: {path}")
            if sha256(path) != expected["sha256"]:
                raise ReviewFailure(f"raw file hash drifted: {path}")
            raw_files += 1
    if run_count != 30:
        raise ReviewFailure(f"expected 30 runs, got {run_count}")
    return run_count, raw_files


def review_query_text(evidence_dir: Path) -> None:
    for path in sorted((evidence_dir / "remote" / "runs").glob("*/stats-*.json")):
        value = read_json(path)
        statements = value.get("statements", {})
        if statements.get("query_text_exported") is not False:
            raise ReviewFailure(f"query-text boundary failed in {path}")
        for row in statements.get("rows", []):
            if "query" in row:
                raise ReviewFailure(f"query text found in {path}")


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve()
    required = {
        "preflight-evidence.json",
        "remote/capacity-evidence.json",
        "remote-cleanup.json",
        "validation-report.json",
        "negative-report.json",
        "public-summary.json",
    }
    missing = [
        name for name in sorted(required) if not (evidence_dir / name).is_file()
    ]
    if missing:
        raise ReviewFailure(f"required evidence is missing: {missing}")
    capacity = read_json(evidence_dir / "remote" / "capacity-evidence.json")
    validation = read_json(evidence_dir / "validation-report.json")
    negative = read_json(evidence_dir / "negative-report.json")
    public = read_json(evidence_dir / "public-summary.json")
    cleanup = read_json(evidence_dir / "remote-cleanup.json")
    if (
        capacity.get("status") != "passed"
        or validation.get("status") != "passed"
        or negative.get("rejected") != 26
        or cleanup.get("remote_temp_absent") is not True
    ):
        raise ReviewFailure("capacity, validation, negative, or cleanup status failed")
    if (
        capacity.get("cleanup", {}).get("database_absent") is not True
        or capacity.get("cleanup", {}).get("role_absent") is not True
        or capacity.get("cleanup", {}).get("terminated_sessions") != 0
    ):
        raise ReviewFailure("exact database and role cleanup was not proven")
    if (
        capacity.get("production_ch26_gate") != "pending"
        or capacity.get("capacity", {}).get("production_sustainable_tps")
        is not None
        or public.get("production_ch26_gate") != "pending"
        or public.get("production_approval") is not False
    ):
        raise ReviewFailure("production claim boundary failed")
    if any(
        key in json.dumps(public)
        for key in (
            "raw_files",
            "stats-before",
            "stats-after",
            "queryid",
            "application_name",
            "client_addr",
        )
    ):
        raise ReviewFailure("public summary contains a private-evidence field")
    directories, files = review_modes(evidence_dir)
    scanned_bytes = review_secrets(evidence_dir)
    run_count, raw_files = review_raw_manifest(evidence_dir, capacity)
    review_query_text(evidence_dir)
    total_transactions = sum(
        row["pgbench"]["processed_transactions"]
        for row in capacity["experiment"]["runs"]
    )
    print("status=review-ok")
    print(f"run_id={capacity['run_id']}")
    print("matrix_cells=6")
    print(f"measured_runs={run_count}")
    print(f"transactions={total_transactions}")
    print(f"raw_files_verified={raw_files}")
    print(f"counterexamples_rejected={negative['rejected']}")
    print(f"private_directories={directories}")
    print(f"private_files={files}")
    print(f"secret_scan_bytes={scanned_bytes}")
    print("database_cleanup=verified")
    print("role_cleanup=verified")
    print("remote_temp_cleanup=verified")
    print("production_ch26_gate=pending")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReviewFailure, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"chapter 26 review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
