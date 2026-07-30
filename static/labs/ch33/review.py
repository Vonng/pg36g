#!/usr/bin/env python3
"""Review a complete chapter 33 failover/rebuild evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

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
        "raw journal field": re.compile(
            rb'"(?:raw_log|log_lines|log_content)"\s*:',
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
        validation = read_json(args.evidence_root / "validation-report.json")
        negative = read_json(args.evidence_root / "negative-report.json")
        public = read_json(args.evidence_root / "public-summary.json")
        managed = args.evidence_root / "managed"
        manifest = read_json(managed / "drill-manifest.json")
        before = read_json(managed / "before.json")
        failed = read_json(managed / "failed.json")
        rejoined = read_json(managed / "rejoined.json")
        restored = read_json(managed / "restored.json")
        fence = read_json(managed / "old-primary-fence.json")
        client = read_json(managed / "client-reconciliation.json")
        tabletop = read_json(managed / "dcs-tabletop.json")
        rebuild = read_json(args.evidence_root / "rebuild.json")

        if (
            validation.get("passed") is not True
            or validation.get("failure_count") != 0
            or validation.get("declared_counterexamples") != 33
            or validation.get("live_evidence_mutants") != 33
            or validation.get("live_evidence_mutants_rejected") != 33
            or validation.get("source_files_hash_bound") != 15
            or validation.get("production_ch33_gate") != "pending"
        ):
            raise ReviewError("positive failover validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 33
            or negative.get("rejected_count") != 33
            or negative.get("live_mutant_count") != 33
            or negative.get("live_mutants_rejected") != 33
        ):
            raise ReviewError("adversarial failover validation failed")

        selected = failed.get("selected_leader")
        if selected not in {"pg-test-2", "pg-test-3"}:
            raise ReviewError("runtime candidate is not an eligible replica")
        if (
            manifest.get("run_id") != public.get("run_id")
            or manifest.get("run_id") != rebuild.get("run_id")
            or client.get("run_id") != public.get("run_id")
            or tabletop.get("run_id") != public.get("run_id")
            or validation.get("run_id") != public.get("run_id")
        ):
            raise ReviewError("run identity binding drifted")
        if (
            fence.get("service_active") is not False
            or fence.get("postmaster_alive") is not False
            or fence.get("patroni_rest_reachable") is not False
            or client.get("acknowledged_missing") != 0
            or client.get("duplicate_tokens") != 0
            or client.get("unreconciled_unknown_outcomes") != 0
        ):
            raise ReviewError("fence or client reconciliation drifted")
        if (
            before["phase"] != "before"
            or failed["phase"] != "failed"
            or rejoined["phase"] != "rejoined"
            or restored["phase"] != "restored"
            or public["managed_failover"]["selected_candidate"]
            != selected
            or public["managed_failover"]["candidate_forced"] is not False
            or public["managed_failover"][
                "old_primary_rejoined_streaming"
            ]
            is not True
            or public["managed_failover"]["baseline_restored_to"]
            != "pg-test-1"
        ):
            raise ReviewError("managed topology narrative drifted")
        if (
            rebuild.get("same_system_identifier") is not True
            or rebuild.get("timeline_diverged") is not True
            or rebuild.get("rewind_target_has_new_primary") is not True
            or rebuild.get("rewind_target_has_old_divergent") is not False
            or rebuild.get("basebackup_target_streaming") is not True
            or rebuild.get("cleanup", {}).get("root_exists_after")
            is not False
        ):
            raise ReviewError("disposable rebuild proof drifted")

        safety = public.get("safety", {})
        required_false = (
            "managed_pgdata_deleted",
            "managed_reinit_executed",
            "dcs_changed",
            "network_partition_injected",
            "route_changed",
            "hardware_fence_claimed",
            "raw_patroni_log_exported",
        )
        if (
            safety.get(
                "old_primary_process_fenced_before_acceptance"
            )
            is not True
            or any(safety.get(key) is not False for key in required_false)
            or safety.get("secret_values_exported") != 0
            or safety.get("fixture_schema_removed") is not True
            or safety.get("external_dispatch_count") != 0
        ):
            raise ReviewError("public safety boundary drifted")
        decision = public.get("decision", {})
        if (
            decision.get("production_approval") is not None
            or decision.get("production_ch33_gate") != "pending"
        ):
            raise ReviewError("production chapter gate opened")
        if (
            tabletop.get("live_dcs_fault_injected") is not False
            or tabletop.get("live_network_partition_injected") is not False
            or tabletop.get("leader_key_deleted") is not False
        ):
            raise ReviewError("DCS tabletop performed a live mutation")

        contract = (
            args.source_dir / "lab-contract.md"
        ).read_text(encoding="utf-8")
        for token in (
            "controlled process fence",
            "watchdog 为 off",
            "不停止、重启或改写 etcd",
            "两个分叉 primary **从不同时运行**",
            "不会执行 `patronictl reinit`",
            "production_ch33_gate=pending",
        ):
            if token not in contract:
                raise ReviewError(
                    f"lab contract safety token missing: {token}"
                )

        public_source = args.source_dir / "failover-run.json"
        if public_source.is_file():
            source_value = read_json(public_source)
            if (
                source_value.get("status") != "pending-formal-run"
                and source_value != public
            ):
                raise ReviewError(
                    "published failover-run.json differs from public summary"
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
                "selected_candidate": selected,
                "managed_timeline": [
                    public["managed_failover"]["initial_timeline"],
                    public["managed_failover"]["failover_timeline"],
                    public["managed_failover"]["restored_timeline"],
                ],
                "client_maximum_ack_gap_ms": public["client"][
                    "maximum_ack_gap_ms"
                ],
                "pg_rewind_ms": public["rebuild"]["pg_rewind_ms"],
                "fresh_basebackup_ms": public["rebuild"][
                    "fresh_basebackup_ms"
                ],
                "declared_counterexamples_rejected": 33,
                "live_mutants_rejected": 33,
                "source_files_hash_bound": 15,
                "files_verified": files,
                "bytes_verified": bytes_seen,
                "secret_material": "absent",
                "production_ch33_gate": "pending",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
