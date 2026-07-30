#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    pass


SOURCE_FILES = [
    "requirements.json",
    "upgrade-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "remote_experiment.py",
    "validate.py",
    "review.py",
    "task.sh",
]


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewError(f"JSON is not an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    args = parser.parse_args()

    evidence_dir = args.evidence_dir.resolve()
    source_dir = args.source_dir.resolve()
    required = [
        evidence_dir / "preflight-evidence.json",
        evidence_dir / "remote" / "upgrade-evidence.json",
        evidence_dir / "remote" / "fixture-cleanup.json",
        evidence_dir / "remote" / "pg-upgrade-check-rejected.log",
        evidence_dir / "remote" / "pg-upgrade-check-passed.log",
        evidence_dir / "remote" / "pg-upgrade-copy.log",
        evidence_dir / "remote" / "source-checksums.log",
        evidence_dir / "remote" / "post-upgrade-analyze.log",
        evidence_dir / "remote-cleanup.json",
        evidence_dir / "negative-report.json",
        evidence_dir / "validation-report.json",
        evidence_dir / "public-summary.json",
    ]
    for path in required:
        require(path.is_file(), f"required evidence missing: {path}")

    preflight = load_json(evidence_dir / "preflight-evidence.json")
    upgrade = load_json(
        evidence_dir / "remote" / "upgrade-evidence.json"
    )
    fixture_cleanup = load_json(
        evidence_dir / "remote" / "fixture-cleanup.json"
    )
    remote_cleanup = load_json(evidence_dir / "remote-cleanup.json")
    negative = load_json(evidence_dir / "negative-report.json")
    validation = load_json(evidence_dir / "validation-report.json")
    public = load_json(evidence_dir / "public-summary.json")

    require(validation.get("status") == "validation-ok",
            "validation report is not successful")
    require(validation.get("mode") == "complete",
            "validation report is not complete")
    require(validation.get("declared_counterexamples_rejected") == 30,
            "declared counterexample count mismatch")
    require(validation.get("live_evidence_mutants_rejected") == 20,
            "live mutant count mismatch")
    require(len(negative.get("declared", [])) == 30,
            "negative declared report count mismatch")
    require(len(negative.get("live", [])) == 20,
            "negative live report count mismatch")
    require(
        all(item.get("status") == "rejected"
            for item in negative["declared"] + negative["live"]),
        "negative report contains accepted case",
    )

    run_id = upgrade.get("run_id")
    require(run_id == fixture_cleanup.get("run_id"),
            "fixture cleanup run ID differs")
    require(run_id == remote_cleanup.get("run_id"),
            "remote cleanup run ID differs")
    require(run_id == public.get("run_id"),
            "public summary run ID differs")
    require(
        upgrade.get("preflight_run_id")
        == preflight.get("preflight_run_id")
        == public.get("preflight_run_id"),
        "preflight binding differs",
    )
    require(
        public["decision"]["production_ch30_gate"] == "pending",
        "public production gate changed",
    )
    require(public["upgrade"]["method"] == "copy",
            "public upgrade method changed")
    require(public["rollback"]["proven_before_target_writes"] is True,
            "public rollback proof missing")
    require(public["cleanup"]["remote_root_absent"] is True,
            "public cleanup claim missing")

    current_hashes = {
        name: sha256_file(source_dir / name)
        for name in SOURCE_FILES
    }
    require(
        current_hashes == preflight.get("source_hashes"),
        "source files changed after preflight",
    )

    public_text = (evidence_dir / "public-summary.json").read_text(
        errors="replace"
    )
    for forbidden in [
        "/tmp/",
        "password=",
        "conninfo",
        "BEGIN PRIVATE KEY",
        "old_share",
        "old_bin",
        "new_bin",
    ]:
        require(forbidden not in public_text,
                f"public summary leaks private detail: {forbidden}")

    total_bytes = 0
    file_count = 0
    for path in evidence_dir.rglob("*"):
        if not path.is_file():
            continue
        file_count += 1
        total_bytes += path.stat().st_size
        mode = path.stat().st_mode & 0o777
        require(mode & 0o077 == 0,
                f"evidence file is group/world accessible: {path}")
        text = path.read_text(errors="replace")
        for forbidden in ["password=", "BEGIN PRIVATE KEY"]:
            require(forbidden not in text,
                    f"secret-like material found in {path.name}")

    require(fixture_cleanup.get("run_root_absent") is True,
            "fixture run root remains")
    require(remote_cleanup.get("remote_root_absent") is True,
            "remote root remains")
    require(remote_cleanup.get("active_postmasters") == [],
            "temporary postmaster remains")

    print(
        json.dumps(
            {
                "status": "review-ok",
                "run_id": run_id,
                "files_verified": file_count,
                "bytes_verified": total_bytes,
                "source_files_hash_bound": len(current_hashes),
                "declared_counterexamples_rejected": 30,
                "live_mutants_rejected": 20,
                "collation_gate_repaired":
                    public["collation_gate"]["mismatch_after"] is False,
                "checksum_mismatch_rejected":
                    public["incompatible_target"]["rejected"],
                "copy_upgrade_complete":
                    public["upgrade"]["complete"],
                "rollback_proven":
                    public["rollback"][
                        "proven_before_target_writes"
                    ],
                "temporary_cleanup": "verified",
                "production_ch30_gate": "pending",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    try:
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"review failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
