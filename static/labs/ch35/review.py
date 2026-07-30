#!/usr/bin/env python3
"""Review a complete chapter 35 forensic evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

from common import LabError, read_json


class ReviewError(RuntimeError):
    """Raised when forensic evidence is unsafe or inconsistent."""


def require_private(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ReviewError(
            f"evidence is group/world accessible: {path} ({mode:04o})"
        )


def scan_secret_material(root: Path) -> tuple[int, int]:
    patterns = {
        "SCRAM verifier": re.compile(rb"SCRAM-SHA-256\$"),
        "private key": re.compile(
            rb"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----"
        ),
        "clear password field": re.compile(
            rb'"password"\s*:\s*"(?!REDACTED|REPLACE_)',
            re.IGNORECASE,
        ),
        "credential-bearing URI": re.compile(
            rb"(?:postgres|postgresql|https?)://"
            rb"[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
        "raw error or log": re.compile(
            rb'"(?:raw_error|raw_log|log_lines|stderr)"\s*:',
            re.IGNORECASE,
        ),
    }
    require_private(root)
    files = 0
    bytes_seen = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        require_private(path)
        payload = path.read_bytes()
        files += 1
        bytes_seen += len(payload)
        for label, pattern in patterns.items():
            if pattern.search(payload):
                raise ReviewError(
                    f"{label} found in private evidence: {path}"
                )
    return files, bytes_seen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validation = read_json(
            args.evidence_root / "validation-report.json"
        )
        negative = read_json(args.evidence_root / "negative-report.json")
        public = read_json(args.evidence_root / "public-summary.json")
        exercise = read_json(
            args.evidence_root / "exercise" / "exercise-evidence.json"
        )
        manifest = read_json(
            args.evidence_root / "exercise" / "run-manifest.json"
        )
        cleanup = read_json(
            args.evidence_root / "exercise" / "cleanup.json"
        )
        source_manifest = read_json(
            args.evidence_root / "exercise" / "source-manifest.json"
        )
        classification = read_json(
            args.evidence_root / "classification.json"
        )

        if (
            validation.get("passed") is not True
            or validation.get("failure_count") != 0
            or validation.get("declared_counterexamples") != 35
            or validation.get("live_evidence_mutants") != 35
            or validation.get("live_evidence_mutants_rejected") != 35
            or validation.get("source_files_hash_bound") != 13
            or validation.get("production_ch35_gate") != "pending"
        ):
            raise ReviewError("positive forensic validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 35
            or negative.get("rejected_count") != 35
            or negative.get("live_mutant_count") != 35
            or negative.get("live_mutants_rejected") != 35
        ):
            raise ReviewError("adversarial forensic validation failed")
        if (
            exercise.get("run_id") != public.get("run_id")
            or exercise.get("run_id") != manifest.get("run_id")
            or exercise.get("run_id") != validation.get("run_id")
            or classification.get("hidden_answers_read") is not False
        ):
            raise ReviewError("run identity or blind provenance drifted")
        if (
            public.get("status") != "completed"
            or public.get("experiment", {}).get("blind_classification")
            is not True
            or set(
                public.get("experiment", {}).get("randomized_order", [])
            )
            != {"PHYSICAL_HEAP_PAGE", "COLLATION_METADATA"}
            or public.get("experiment", {}).get("fixture_rows") != 12000
        ):
            raise ReviewError("public experiment projection drifted")
        physical = public.get("physical_page", {})
        if (
            physical.get("route") != "RESTORE_FROM_KNOWN_GOOD_COPY"
            or physical.get("relation_kind") != "heap"
            or physical.get("bytes_changed") != 1
            or physical.get("offline_bad_checksums", 0) < 1
            or physical.get("online_scan_succeeded") is not False
            or physical.get("in_place_repair") is not False
            or physical.get("recovered_invariants_match") is not True
            or physical.get("recovered_bad_checksums") != 0
            or physical.get("original_case_preserved") is not True
        ):
            raise ReviewError("physical-page recovery evidence drifted")
        derived = public.get("collation_derived", {})
        if (
            derived.get("route") != "REINDEX_AND_REFRESH_COLLATION"
            or derived.get("offline_bad_checksums") != 0
            or derived.get("structural_amcheck_before") is not True
            or derived.get("reindex_before_refresh") is not True
            or derived.get("version_mismatch_after") is not False
            or derived.get("recovered_invariants_match") is not True
            or derived.get("original_case_preserved") is not True
        ):
            raise ReviewError("collation-derived recovery evidence drifted")
        managed = public.get("managed_cluster", {})
        if (
            managed.get("topology_unchanged") is not True
            or managed.get("system_identifier_unchanged") is not True
            or managed.get("timeline_unchanged") is not True
            or managed.get("mutations") != 0
        ):
            raise ReviewError("managed cluster boundary drifted")
        safety = public.get("safety", {})
        false_keys = (
            "managed_postgresql_mutated",
            "managed_pgdata_mutated",
            "managed_service_changed",
            "managed_route_changed",
            "managed_reset_host_executed",
            "unique_source_mutated",
            "manual_pg_wal_file_deletion",
            "ignore_checksum_failure_used",
            "zero_damaged_pages_used",
            "pg_resetwal_used",
            "wrong_action_executed",
            "production_data_touched",
            "production_traffic_touched",
        )
        if (
            any(safety.get(key) is not False for key in false_keys)
            or safety.get("external_dispatch_count") != 0
            or safety.get("known_good_snapshot_unchanged") is not True
            or safety.get("exact_root_removed") is not True
            or cleanup.get("root_exists_after") is not False
        ):
            raise ReviewError("forensic safety or cleanup drifted")
        if (
            manifest.get("managed_reset_host_executed") is not False
            or manifest.get("production_ch35_gate") != "pending"
            or public.get("decision", {}).get("production_approval")
            is not None
            or public.get("decision", {}).get("production_ch35_gate")
            != "pending"
        ):
            raise ReviewError("managed reset or production gate opened")
        if (
            source_manifest.get("schema")
            != "pg36-ch35-source-manifest-v1"
            or len(source_manifest.get("files", [])) != 13
        ):
            raise ReviewError("source manifest drifted")

        published = args.source_dir / "rescue-run.json"
        if published.is_file():
            value = read_json(published)
            if (
                value.get("status") != "pending-formal-run"
                and value != public
            ):
                raise ReviewError(
                    "published rescue-run.json differs from public summary"
                )
        files, bytes_seen = scan_secret_material(args.evidence_root)
    except (
        KeyError,
        TypeError,
        OSError,
        LabError,
        ReviewError,
    ) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "review-ok",
                "run_id": public["run_id"],
                "scenario_order": public["experiment"][
                    "randomized_order"
                ],
                "physical_bad_checksums": physical[
                    "offline_bad_checksums"
                ],
                "physical_sqlstate": physical[
                    "online_scan_sqlstate"
                ],
                "collation_repair_elapsed_ms": derived[
                    "repair_elapsed_ms"
                ],
                "declared_counterexamples_rejected": 35,
                "live_mutants_rejected": 35,
                "source_files_hash_bound": 13,
                "files_verified": files,
                "bytes_verified": bytes_seen,
                "secret_material": "absent",
                "managed_reset_host_executed": False,
                "production_ch35_gate": "pending",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
