#!/usr/bin/env python3
"""Independently review a complete chapter 27 evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from capture import SOURCE_NAMES


class ReviewError(RuntimeError):
    pass


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def walk_keys(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    result: list[tuple[str, ...]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (str(key),)
            result.append(child_path)
            result.extend(walk_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(walk_keys(child, path + (str(index),)))
    return result


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve()
    source_dir = args.source_dir.resolve()
    required = {
        "preflight": evidence_dir / "preflight-evidence.json",
        "tuning": evidence_dir / "remote" / "tuning-evidence.json",
        "cleanup": evidence_dir / "remote-cleanup.json",
        "validation": evidence_dir / "validation-report.json",
        "negative": evidence_dir / "negative-report.json",
        "public": evidence_dir / "public-summary.json",
    }
    for label, path in required.items():
        require(path.is_file(), f"missing {label}: {path}")
    preflight = read_json(required["preflight"])
    tuning = read_json(required["tuning"])
    cleanup = read_json(required["cleanup"])
    validation = read_json(required["validation"])
    negative = read_json(required["negative"])
    public = read_json(required["public"])
    current_hashes = {
        name: sha256(source_dir / name)
        for name in SOURCE_NAMES
    }
    require(
        current_hashes == preflight["source_hashes"],
        "source hashes diverged from preflight",
    )
    require(
        validation["status"] == "passed"
        and validation["mode"] == "full"
        and validation["run_id"] == tuning["run_id"],
        "validation report mismatch",
    )
    require(
        negative["positive_model_passed"] is True
        and negative["counterexamples"] == 28
        and negative["all_rejected"] is True,
        "adversarial validation mismatch",
    )
    require(
        cleanup["remote_temp_absent"] is True
        and tuning["cleanup"]["database_absent"] is True
        and tuning["cleanup"]["role_absent"] is True
        and tuning["cleanup"]["unrelated_sessions_terminated"] == 0
        and tuning["cleanup"]["drop_with_force_used"] is False,
        "cleanup proof mismatch",
    )
    runs = tuning["runs"]
    require(len(runs) == 10, "measured run count mismatch")
    ratios = []
    for repetition in range(1, 6):
        baseline = next(
            row for row in runs
            if row["mode"] == "auto" and row["repetition"] == repetition
        )
        candidate = next(
            row for row in runs
            if row["mode"] == "force_generic_plan"
            and row["repetition"] == repetition
        )
        require(baseline["seed"] == candidate["seed"], "paired seed mismatch")
        ratios.append(
            candidate["pgbench"]["tps"] / baseline["pgbench"]["tps"]
        )
    require(
        math.isclose(
            statistics.median(ratios),
            public["experiment"]["paired_tps_ratio_median"],
            rel_tol=1e-12,
            abs_tol=1e-12,
        ),
        "public paired effect does not match raw run summaries",
    )
    require(
        public["decision"]["result"] == tuning["summary"]["decision"]
        and public["decision"]["persistent_change_applied"] is False
        and public["decision"]["production_ch27_gate"] == "pending",
        "public decision boundary mismatch",
    )
    require(
        public["hypothesis"]["scope"] == "benchmark-session-only"
        and public["hypothesis"]["persistent_configuration_change"] is False
        and public["validation"]["raw_transaction_logs_public"] is False,
        "public scope or raw-evidence boundary mismatch",
    )
    forbidden_key_patterns = (
        re.compile(r"(?:password|passwd|credential)", re.I),
        re.compile(r"conn(ection)?_?(string|uri)", re.I),
        re.compile(r"query(_text)?$", re.I),
        re.compile(r"sourcefile", re.I),
        re.compile(r"raw_?(payload|sql|transaction)", re.I),
    )
    allowed_boolean_keys = {
        "raw_transaction_logs_public",
        "raw_settings_paths_public",
        "raw_query_text_public",
    }
    for path in walk_keys(public):
        key = path[-1]
        if key in allowed_boolean_keys:
            continue
        require(
            not any(pattern.search(key) for pattern in forbidden_key_patterns),
            f"forbidden public key: {'.'.join(path)}",
        )
    serialized_public = json.dumps(public, sort_keys=True)
    secret_patterns = (
        r"postgres(?:ql)?://",
        r"PGPASSWORD",
        r"password\s*[=:]",
        r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY",
    )
    require(
        not any(re.search(pattern, serialized_public, re.I) for pattern in secret_patterns),
        "public summary contains secret-shaped material",
    )
    files = [path for path in evidence_dir.rglob("*") if path.is_file()]
    require(files, "evidence bundle is empty")
    for path in files:
        mode = os.stat(path).st_mode & 0o777
        require(mode & 0o077 == 0, f"private artifact is too permissive: {path}")
    secret_hits = []
    total_bytes = 0
    for path in files:
        payload = path.read_bytes()
        total_bytes += len(payload)
        if b"\x00" in payload:
            continue
        text = payload.decode("utf-8", errors="replace")
        for pattern in secret_patterns:
            if re.search(pattern, text, re.I):
                secret_hits.append(f"{path}:{pattern}")
    require(not secret_hits, f"private evidence secret scan failed: {secret_hits[:5]}")
    raw_logs = list((evidence_dir / "remote" / "runs").glob("*/transactions.*"))
    require(len(raw_logs) >= 20, "raw transaction log inventory is incomplete")
    print("status=review-ok")
    print(f"run_id={tuning['run_id']}")
    print("tested_parameters=1")
    print("measured_runs=10")
    print(f"transactions={public['experiment']['transactions']}")
    print(f"decision={public['decision']['result']}")
    print("persistent_change_applied=false")
    print("counterexamples=28-rejected")
    print(f"raw_transaction_logs={len(raw_logs)}")
    print(f"private_bytes_scanned={total_bytes}")
    print("fixture_cleanup=verified")
    print("remote_temp_cleanup=verified")
    print("production_ch27_gate=pending")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ReviewError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        StopIteration,
    ) as exc:
        print(f"chapter 27 review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
