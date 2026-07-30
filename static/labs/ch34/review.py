#!/usr/bin/env python3
"""Review a complete chapter 34 evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

from common import LabError, read_json


class ReviewError(RuntimeError):
    """Raised when evidence is unsafe or internally inconsistent."""


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
        "authorization header": re.compile(
            rb"authorization\s*:\s*(?:basic|bearer)\s+\S+",
            re.IGNORECASE,
        ),
        "raw log payload": re.compile(
            rb'"(?:raw_log|log_lines|log_content|stderr)"\s*:',
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
        before = read_json(args.evidence_root / "before.json")
        after = read_json(args.evidence_root / "after.json")
        classification = read_json(
            args.evidence_root / "classification.json"
        )
        exercise_root = args.evidence_root / "exercise"
        exercise = read_json(exercise_root / "exercise-evidence.json")
        manifest = read_json(exercise_root / "run-manifest.json")
        cleanup = read_json(exercise_root / "cleanup.json")
        source_manifest = read_json(
            exercise_root / "source-manifest.json"
        )

        if (
            validation.get("passed") is not True
            or validation.get("failure_count") != 0
            or validation.get("declared_counterexamples") != 34
            or validation.get("live_evidence_mutants") != 34
            or validation.get("live_evidence_mutants_rejected") != 34
            or validation.get("source_files_hash_bound") != 12
            or validation.get("production_ch34_gate") != "pending"
        ):
            raise ReviewError("positive overload validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 34
            or negative.get("rejected_count") != 34
            or negative.get("live_mutant_count") != 34
            or negative.get("live_mutants_rejected") != 34
        ):
            raise ReviewError("adversarial overload validation failed")
        if (
            exercise.get("run_id") != public.get("run_id")
            or exercise.get("run_id") != manifest.get("run_id")
            or exercise.get("run_id") != validation.get("run_id")
            or classification.get("input_case_count") != 2
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
            != {"FLOW", "RETENTION"}
            or public.get("flow_pressure", {}).get("classified_route")
            != "RELIEVE_FLOW_PRESSURE"
            or public.get("wal_retention", {}).get("classified_route")
            != "PRESERVE_RETENTION_EVIDENCE"
        ):
            raise ReviewError("public root-cause result drifted")
        if (
            public.get("flow_pressure", {}).get(
                "connection_rejections",
                0,
            )
            < 1
            or public.get("flow_pressure", {}).get(
                "observed_sessions",
                0,
            )
            < 18
            or public.get("flow_pressure", {}).get("lock_waiters", 0)
            < 1
            or public.get("flow_pressure", {}).get(
                "post_fixture_sessions"
            )
            != 0
        ):
            raise ReviewError("flow evidence lower bound drifted")
        if (
            public.get("wal_retention", {}).get(
                "inactive_physical_slots"
            )
            != 1
            or public.get("wal_retention", {}).get(
                "retained_wal_bytes",
                0,
            )
            < 33_554_432
            or public.get("wal_retention", {}).get(
                "retained_wal_bytes",
                0,
            )
            > 134_217_728
            or public.get("wal_retention", {}).get(
                "post_physical_slots"
            )
            != 0
            or public.get("wal_retention", {}).get(
                "manual_pg_wal_file_deletion"
            )
            is not False
        ):
            raise ReviewError("WAL retention evidence boundary drifted")
        managed = public.get("managed_cluster", {})
        if (
            managed.get("topology_unchanged") is not True
            or managed.get("system_identifier_unchanged") is not True
            or managed.get("timeline_unchanged") is not True
            or managed.get("mutations") != 0
            or before.get("mutation") != "none"
            or after.get("mutation") != "none"
        ):
            raise ReviewError("managed cluster boundary drifted")
        safety = public.get("safety", {})
        required_false = (
            "managed_postgresql_mutated",
            "managed_connection_storm",
            "managed_replication_slot_created",
            "managed_query_canceled",
            "managed_service_changed",
            "managed_route_changed",
            "host_cache_dropped",
            "oom_injected",
            "filesystem_fill_injected",
            "wrong_action_executed",
            "manual_pg_wal_file_deletion",
            "production_data_touched",
            "production_traffic_touched",
        )
        if (
            any(safety.get(key) is not False for key in required_false)
            or safety.get("external_dispatch_count") != 0
            or safety.get("exact_root_removed") is not True
            or cleanup.get("root_exists_after") is not False
        ):
            raise ReviewError("exercise safety or exact cleanup drifted")
        if (
            public.get("decision", {}).get("production_approval")
            is not None
            or public.get("decision", {}).get("production_ch34_gate")
            != "pending"
            or manifest.get("production_ch34_gate") != "pending"
        ):
            raise ReviewError("production chapter gate opened")
        if (
            source_manifest.get("schema")
            != "pg36-ch34-source-manifest-v1"
            or len(source_manifest.get("files", [])) != 12
        ):
            raise ReviewError("source manifest drifted")

        public_source = args.source_dir / "overload-run.json"
        if public_source.is_file():
            source_value = read_json(public_source)
            if (
                source_value.get("status") != "pending-formal-run"
                and source_value != public
            ):
                raise ReviewError(
                    "published overload-run.json differs from public summary"
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
                "flow_observed_sessions": public["flow_pressure"][
                    "observed_sessions"
                ],
                "flow_connection_rejections": public["flow_pressure"][
                    "connection_rejections"
                ],
                "retained_wal_bytes": public["wal_retention"][
                    "retained_wal_bytes"
                ],
                "declared_counterexamples_rejected": 34,
                "live_mutants_rejected": 34,
                "source_files_hash_bound": 12,
                "files_verified": files,
                "bytes_verified": bytes_seen,
                "secret_material": "absent",
                "production_ch34_gate": "pending",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
