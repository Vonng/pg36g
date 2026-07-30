#!/usr/bin/env python3
"""Review a complete chapter 31 incident-response evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    """Raised when a complete bundle is unsafe or internally inconsistent."""


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
        "raw SQL field": re.compile(
            rb'"(?:query|raw_sql|sql_text|bind_values)"\s*:\s*',
            re.IGNORECASE,
        ),
        "raw log field": re.compile(
            rb'"(?:raw_log|log_lines|log_content)"\s*:\s*',
            re.IGNORECASE,
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
        exercise = read_json(
            args.evidence_root / "exercise-evidence.json"
        )
        blind = read_json(
            args.evidence_root / "blind-packets.json"
        )
        responses = read_json(
            args.evidence_root / "responses.json"
        )
        facilitator = read_json(
            args.evidence_root / "facilitator-pack.json"
        )

        if (
            validation.get("passed") is not True
            or validation.get("failure_count") != 0
            or validation.get("declared_counterexamples") != 31
            or validation.get("live_evidence_mutants") != 18
            or validation.get("scenario_count") != 8
            or validation.get("source_files_hash_bound") != 12
            or validation.get("production_ch31_gate") != "pending"
        ):
            raise ReviewError("positive incident validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 31
            or negative.get("rejected_count") != 31
            or negative.get("live_mutant_count") != 18
            or negative.get("live_mutants_rejected") != 18
        ):
            raise ReviewError("adversarial incident validation failed")
        if (
            any(value is not False for value in preflight["claims"].values())
            or exercise.get("online_mutation") != "none"
            or exercise.get("real_incident_injected") is not False
            or exercise.get("human_competency_claimed") is not False
            or exercise.get("production_ch31_gate") != "pending"
        ):
            raise ReviewError("evidence overclaims an incident action")
        safety = public.get("safety", {})
        if (
            safety.get("sql_transaction") != "READ ONLY"
            or safety.get("online_mutation") != "none"
            or any(
                value is not False
                for key, value in safety.items()
                if key not in {"sql_transaction", "online_mutation"}
            )
        ):
            raise ReviewError("public safety boundary drifted")
        table = public.get("tabletop", {})
        if (
            table.get("scenario_library") != 8
            or table.get("drawn_cases") != 2
            or table.get("modes") != ["solo", "team"]
            or len(set(table.get("routes", []))) != 2
            or table.get("first_response_minutes") != 15
            or table.get("human_competency_claimed") is not False
        ):
            raise ReviewError("public tabletop summary drifted")
        decision = public.get("decision", {})
        if (
            decision.get("production_approval") is not None
            or decision.get("production_ch31_gate") != "pending"
        ):
            raise ReviewError("public production gate opened")
        if (
            blind.get("preflight_run_id") != preflight.get("run_id")
            or responses.get("preflight_run_id") != preflight.get("run_id")
            or facilitator.get("preflight_run_id")
            != preflight.get("run_id")
            or exercise.get("preflight_run_id")
            != preflight.get("run_id")
            or public.get("preflight_run_id")
            != preflight.get("run_id")
            or public.get("run_id") != exercise.get("run_id")
        ):
            raise ReviewError("run identity binding drifted")
        if any(
            row.get("dangerous_actions_executed") != []
            or row.get("production_authorized") is not False
            for row in responses.get("responses", [])
        ):
            raise ReviewError("reference response crossed safety boundary")

        contract_text = (
            args.source_dir / "lab-contract.md"
        ).read_text(encoding="utf-8")
        for token in (
            "L0-read-only",
            "不会暂停 Patroni",
            "不证明任何真人",
            "READ ONLY",
            "production_ch31_gate=pending",
        ):
            if token not in contract_text:
                raise ReviewError(
                    f"lab contract safety token missing: {token}"
                )
        files, bytes_seen = scan_secret_material(args.evidence_root)
    except (OSError, KeyError, ReviewError) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1

    environment = public["environment"]
    print(
        json.dumps(
            {
                "bytes_verified": bytes_seen,
                "cluster": environment["cluster"],
                "declared_counterexamples_rejected": 31,
                "files_verified": files,
                "live_mutants_rejected": 18,
                "modes": public["tabletop"]["modes"],
                "online_mutation": "none",
                "production_ch31_gate": "pending",
                "routes": public["tabletop"]["routes"],
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
