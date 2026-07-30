#!/usr/bin/env python3
"""Independently review a completed chapter 32 evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    """Raised when evidence is unsafe or internally inconsistent."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def require_private(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ReviewError(
            f"evidence is group/world accessible: {path} ({mode:04o})"
        )


def scan_evidence(root: Path) -> tuple[int, int]:
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
        "raw system identifier": re.compile(
            rb'"system_identifier"\s*:\s*"[0-9]+"'
        ),
    }
    require_private(root)
    file_count = 0
    byte_count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        require_private(path)
        data = path.read_bytes()
        file_count += 1
        byte_count += len(data)
        for label, pattern in patterns.items():
            if pattern.search(data):
                raise ReviewError(
                    f"{label} found in private evidence: {path}"
                )
    return file_count, byte_count


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
        negative = read_json(
            args.evidence_root / "negative-report.json"
        )
        public = read_json(
            args.evidence_root / "public-summary.json"
        )
        preflight = read_json(
            args.evidence_root / "preflight-evidence.json"
        )
        manifest = read_json(
            args.evidence_root / "exercise-manifest.json"
        )
        inclusive = read_json(
            args.evidence_root / "inclusive-recovery.json"
        )
        exclusive = read_json(
            args.evidence_root / "exclusive-recovery.json"
        )
        reconciliation = read_json(
            args.evidence_root / "reconciliation.json"
        )
        cleanup = read_json(
            args.evidence_root / "cleanup.json"
        )

        if (args.evidence_root / "failure.json").exists():
            raise ReviewError("failure evidence remains in completed bundle")
        if (
            validation.get("passed") is not True
            or validation.get("failure_count") != 0
            or validation.get("declared_counterexamples") != 32
            or validation.get("live_evidence_mutants") != 32
            or validation.get("source_files_hash_bound") != 12
            or validation.get("production_ch32_gate") != "pending"
        ):
            raise ReviewError("positive PITR validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 32
            or negative.get("rejected_count") != 32
            or negative.get("live_mutant_count") != 32
            or negative.get("live_mutants_rejected") != 32
        ):
            raise ReviewError("adversarial PITR validation failed")

        if (
            preflight.get("mutation") != "none"
            or any(
                value is not False
                for value in preflight.get("claims", {}).values()
            )
            or manifest.get("managed_pgdata_touched") is not False
            or manifest.get("patroni_changed") is not False
            or manifest.get("dcs_changed") is not False
            or manifest.get("route_changed") is not False
            or manifest.get("business_cutover_performed") is not False
        ):
            raise ReviewError("exercise crossed its safety boundary")
        if (
            inclusive.get("target_inclusive") is not True
            or inclusive.get("accepted") is not False
            or exclusive.get("target_inclusive") is not False
            or exclusive.get("accepted") is not True
        ):
            raise ReviewError("candidate decision is not evidence-bound")
        if (
            reconciliation.get(
                "raw_exclusive_missing_legitimate_writes"
            )
            != 100
            or reconciliation.get("audited_post_target_rows") != 100
            or reconciliation.get(
                "reconciled_fixture_data_loss_rows"
            )
            != 0
            or reconciliation.get("external_dispatch_count") != 0
            or reconciliation.get("business_cutover_performed")
            is not False
        ):
            raise ReviewError("reconciliation claim drifted")
        if (
            cleanup.get("fixture_schema_removed") is not True
            or cleanup.get("exact_restore_roots_removed") is not True
            or cleanup.get("backup_retained") is not True
            or cleanup.get("backup_expired") is not False
            or cleanup.get("archived_wal_deleted") is not False
        ):
            raise ReviewError("cleanup or retention claim drifted")

        if (
            public.get("schema") != "pg36-ch32-pitr-run-v1"
            or public.get("run_id") != manifest.get("run_id")
            or public.get("preflight_run_id") != preflight.get("run_id")
            or public.get("candidates", {})
            .get("inclusive", {})
            .get("accepted")
            is not False
            or public.get("candidates", {})
            .get("exclusive", {})
            .get("accepted")
            is not True
            or public.get("reconciliation", {}).get(
                "post_target_rows_preserved"
            )
            != 100
            or public.get("reconciliation", {}).get(
                "reconciled_fixture_data_loss_rows"
            )
            != 0
            or any(
                value not in (False, 0)
                for value in public.get("safety", {}).values()
            )
            or public.get("decision", {}).get("production_approval")
            is not None
            or public.get("decision", {}).get("production_ch32_gate")
            != "pending"
        ):
            raise ReviewError("public summary overclaims the exercise")
        evidence_claim = public.get("evidence", {})
        if (
            evidence_claim.get("declared_counterexamples") != 32
            or evidence_claim.get("live_evidence_mutants") != 32
            or evidence_claim.get("source_files_hash_bound") != 12
            or evidence_claim.get("secret_values_exported") != 0
            or evidence_claim.get("raw_system_identifier_exported")
            is not False
            or evidence_claim.get("production_rto_claimed") is not False
        ):
            raise ReviewError("public evidence claim drifted")

        contract_text = (
            args.source_dir / "lab-contract.md"
        ).read_text(encoding="utf-8")
        for token in (
            "source audit",
            "inclusive XID PITR",
            "exclusive XID",
            "archive-mode=off",
            "不加入 Patroni/DCS",
            "不会 expire 新 backup",
            "production_ch32_gate=pending",
        ):
            if token not in contract_text:
                raise ReviewError(
                    f"lab contract safety token missing: {token}"
                )
        files, bytes_seen = scan_evidence(args.evidence_root)
    except (OSError, KeyError, TypeError, ReviewError) as exc:
        sys.stderr.write(f"review failed: {exc}\n")
        return 1

    print(
        json.dumps(
            {
                "bytes_verified": bytes_seen,
                "cluster": public["environment"]["cluster"],
                "declared_counterexamples_rejected": 32,
                "files_verified": files,
                "inclusive_candidate": "rejected",
                "exclusive_candidate": "accepted",
                "live_mutants_rejected": 32,
                "post_target_rows_preserved": 100,
                "production_ch32_gate": "pending",
                "run_id": public["run_id"],
                "secret_material": "absent",
                "source_files_hash_bound": 12,
                "status": "review-ok",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
