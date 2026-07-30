#!/usr/bin/env python3
"""Review a validated chapter 23 evidence bundle and its source contract."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def require_mode_private(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ReviewError(
            f"evidence is group/world accessible: {path} ({mode:04o})"
        )


def scan_tree(paths: list[Path]) -> None:
    patterns = {
        "SCRAM verifier": re.compile(rb"SCRAM-SHA-256\$"),
        "private key": re.compile(
            rb"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----"
        ),
        "clear password JSON key": re.compile(
            rb'"password"\s*:',
            re.IGNORECASE,
        ),
    }
    for root in paths:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            for label, pattern in patterns.items():
                if pattern.search(data):
                    raise ReviewError(
                        f"{label} found in review scope: {path}"
                    )


def main() -> int:
    args = parse_args()
    drill = args.evidence_root / "drill"
    if not drill.is_dir():
        print("review failed: drill evidence is missing", file=sys.stderr)
        return 1
    try:
        validation = read_json(drill / "validation-report.json")
        negative = read_json(drill / "negative-report.json")
        manifest = read_json(drill / "drill-manifest.json")
        tls = read_json(drill / "tls-tests.json")
        pool = read_json(drill / "pool-context.json")
        rotation = read_json(drill / "rotation-tests.json")
        after = read_json(drill / "after.json")
        if validation.get("passed") is not True:
            raise ReviewError("formal validation did not pass")
        if negative.get("passed") is not True:
            raise ReviewError("counterexample validation did not pass")
        if negative.get("case_count") != 20:
            raise ReviewError("counterexample count drifted")
        if manifest.get("production_gate") != "pending":
            raise ReviewError("production gate was incorrectly passed")
        if (
            manifest.get("mutations_restored", {}).get("pool_settings")
            is not True
            or manifest.get("mutations_restored", {}).get(
                "rotation_login"
            )
            is not False
            or manifest.get("mutations_restored", {}).get(
                "rotation_password"
            )
            is not None
        ):
            raise ReviewError("restoration contract drifted")
        if (
            tls.get("interpretation", {}).get(
                "production_transport_gate"
            )
            != "pending"
        ):
            raise ReviewError("transport gap was hidden")
        if (
            pool.get("session_set_counterexample", {}).get(
                "tenant_a_leaked_to_client_b"
            )
            is not True
        ):
            raise ReviewError("pool leak counterexample is absent")
        if (
            rotation.get("final_state", {}).get("can_login") is not False
            or rotation.get("final_state", {}).get("password_present")
            is not False
        ):
            raise ReviewError("rotation role remains usable")
        topology = after.get("topology", {}).get("members", [])
        leaders = [
            row.get("member")
            for row in topology
            if row.get("role") == "primary"
        ]
        if leaders != ["pg-test-1"]:
            raise ReviewError("retained leader drifted")

        for path in drill.rglob("*"):
            if path.is_file():
                require_mode_private(path)
        # Scanner signatures and parameter names necessarily occur in the
        # validator source. Secret-bearing runtime inputs live outside the
        # repository, so scan the complete evidence tree here and review the
        # source contract structurally below.
        scan_tree([drill])

        reset_text = (
            args.source_dir / "reset-fixture.sh"
        ).read_text(encoding="utf-8")
        for token in (
            "pg36-l2-vagrant/pg-test",
            "PG36_CH23_NONPRODUCTION",
            "PG36_CH23_SYNTHETIC_DATA_ONLY",
            "DROP_CH23_SYNTHETIC_SECURITY_FIXTURE",
        ):
            if token not in reset_text:
                raise ReviewError(f"reset guard is missing: {token}")
    except (OSError, ReviewError) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1

    print("status=review-ok")
    print(f"run_id={manifest['run_id']}")
    print("tenant_rls=pass")
    print("pool_session_leak=reproduced")
    print("transaction_local_context=pass")
    print("credential_rotation=pass")
    print("rotation_role_final_state=nologin-password-null")
    print("pool_settings=restored")
    print("final_leader=pg-test-1")
    print("counterexamples=20-rejected")
    print("production_ch23_gate=pending")
    print("secret_material=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
