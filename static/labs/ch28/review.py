#!/usr/bin/env python3
"""Fail-closed review of a complete chapter 28 evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from capture import SOURCE_NAMES
from validate import public_summary


class ReviewError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve()
    source_dir = args.source_dir.resolve()
    required = {
        "preflight": evidence_dir / "preflight-evidence.json",
        "maintenance": evidence_dir / "remote" / "maintenance-evidence.json",
        "cleanup": evidence_dir / "remote-cleanup.json",
        "validation": evidence_dir / "validation-report.json",
        "negative": evidence_dir / "negative-report.json",
        "public": evidence_dir / "public-summary.json",
        "archive": evidence_dir / "remote" / "events-2024.csv",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ReviewError(f"evidence bundle is incomplete: {missing}")
    preflight = read_json(required["preflight"])
    maintenance = read_json(required["maintenance"])
    cleanup = read_json(required["cleanup"])
    validation = read_json(required["validation"])
    negative = read_json(required["negative"])
    public = read_json(required["public"])
    if validation.get("status") != "passed":
        raise ReviewError("validation report did not pass")
    expected_hashes = {name: sha256(source_dir / name) for name in SOURCE_NAMES}
    if preflight.get("source_hashes") != expected_hashes:
        raise ReviewError("source hash binding failed")
    expected_public = public_summary(
        preflight,
        maintenance,
        negative["declared_rejected"],
    )
    if public != expected_public:
        raise ReviewError("public summary is not the validator allowlist")
    archive = required["archive"]
    if (
        sha256(archive)
        != maintenance["partition_retirement"]["archive"]["sha256"]
        or sum(1 for _ in archive.open(encoding="utf-8")) != 10000
    ):
        raise ReviewError("partition archive integrity failed")
    for path in evidence_dir.rglob("*"):
        if path.is_file():
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise ReviewError(f"private evidence is too permissive: {path}: {mode:o}")
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in evidence_dir.rglob("*")
        if path.is_file() and path.suffix != ".csv"
    )
    secret_markers = (
        "PGPASSWORD=",
        "fixture_password=",
        "password=pg36",
        "BEGIN OPENSSH PRIVATE KEY",
    )
    leaked = [marker for marker in secret_markers if marker in text]
    if leaked:
        raise ReviewError(f"possible secret marker in evidence: {leaked}")
    if (
        maintenance["cleanup"]["database_absent"] is not True
        or maintenance["cleanup"]["role_absent"] is not True
        or cleanup["remote_temp_absent"] is not True
        or public["decision"]["production_ch28_gate"] != "pending"
    ):
        raise ReviewError("cleanup or production gate review failed")
    files = [path for path in evidence_dir.rglob("*") if path.is_file()]
    result = {
        "status": "review-ok",
        "run_id": maintenance["run_id"],
        "files_verified": len(files),
        "bytes_verified": sum(path.stat().st_size for path in files),
        "source_files_hash_bound": len(SOURCE_NAMES),
        "declared_counterexamples_rejected": negative["declared_rejected"],
        "live_mutants_rejected": negative["live_mutants_rejected"],
        "dead_tuples_with_old_snapshot":
            public["mvcc_reclamation"][
                "dead_tuples_after_vacuum_with_old_snapshot"
            ],
        "dead_tuples_after_release":
            public["mvcc_reclamation"]["dead_tuples_after_release_vacuum"],
        "partition_rows_round_tripped":
            public["partition_retirement"]["expired_rows"],
        "fixture_cleanup": "verified",
        "remote_temp_cleanup": "verified",
        "production_ch28_gate": "pending",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
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
    ) as exc:
        print(f"chapter 28 review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
