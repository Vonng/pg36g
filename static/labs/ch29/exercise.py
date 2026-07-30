#!/usr/bin/env python3
"""Upload and run the bounded chapter 29 experiment on the Pigsty meta node."""

from __future__ import annotations

import hashlib
import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from capture import SOURCE_NAMES


class ExerciseError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise ExerciseError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(command[:2])}: {completed.stderr.strip()[-2400:]}"
        )
    return completed


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    evidence_dir = args.evidence_dir.resolve()
    preflight_path = evidence_dir / "preflight-evidence.json"
    if not preflight_path.is_file():
        raise ExerciseError(f"preflight evidence is missing: {preflight_path}")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    expected_clean = {
        "source": {
            "database_absent": True,
            "owner_role_absent": True,
            "runtime_role_absent": True,
            "replication_role_absent": True,
            "slot_absent": True,
        },
        "target": {
            "database_absent": True,
            "owner_role_absent": True,
            "runtime_role_absent": True,
            "subscription_absent": True,
        },
    }
    if (
        preflight.get("schema") != "pg36-ch29-preflight-evidence-v1"
        or preflight.get("mutation") != "none"
        or preflight.get("target")
        != "pg36-l2-vagrant/pg-test-to-pg-meta"
        or preflight.get("clean_start") != expected_clean
        or preflight.get("production_ch29_gate") != "pending"
    ):
        raise ExerciseError("preflight evidence is not acceptable")
    current_hashes = {name: sha256(source_dir / name) for name in SOURCE_NAMES}
    if current_hashes != preflight.get("source_hashes"):
        raise ExerciseError("source changed after preflight")

    token = uuid.uuid4().hex
    remote_root = f"/tmp/pg36-ch29.{token}"
    if not re.fullmatch(r"/tmp/pg36-ch29\.[0-9a-f]{32}", remote_root):
        raise ExerciseError("remote temporary path guard failed")
    source_remote = f"{remote_root}/source"
    output_remote = f"{remote_root}/evidence"
    target = f"{args.ssh_user}@{args.bastion}"
    remote_log = evidence_dir / "remote-experiment.log"
    cleanup_verified = False
    experiment_return_code: int | None = None
    try:
        run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                target,
                "mkdir",
                "-p",
                "-m",
                "700",
                "--",
                source_remote,
            ]
        )
        run(
            [
                "scp",
                "-q",
                *[str(source_dir / name) for name in SOURCE_NAMES],
                f"{target}:{source_remote}/",
            ]
        )
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            target,
            "env",
            "PYTHONDONTWRITEBYTECODE=1",
            "python3",
            f"{source_remote}/remote_experiment.py",
            "--source-dir",
            source_remote,
            "--output-dir",
            output_remote,
        ]
        with remote_log.open("w", encoding="utf-8") as log:
            remote_log.chmod(0o600)
            process = subprocess.Popen(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            experiment_return_code = process.wait()
        local_remote = evidence_dir / "remote"
        if local_remote.exists():
            raise ExerciseError(f"refusing to overwrite {local_remote}")
        probe = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                target,
                "test",
                "-d",
                output_remote,
            ],
            check=False,
        )
        if probe.returncode == 0:
            run(
                [
                    "scp",
                    "-q",
                    "-r",
                    f"{target}:{output_remote}",
                    str(local_remote),
                ],
                check=False,
            )
        if experiment_return_code != 0:
            raise ExerciseError(
                f"remote experiment returned {experiment_return_code}; "
                f"see {remote_log}"
            )
        migration_path = local_remote / "migration-evidence.json"
        route_path = local_remote / "route-history.json"
        if not migration_path.is_file() or not route_path.is_file():
            raise ExerciseError("remote experiment returned incomplete evidence")
        migration = json.loads(migration_path.read_text(encoding="utf-8"))
        source_cleanup = migration.get("cleanup", {}).get("source", {})
        target_cleanup = migration.get("cleanup", {}).get("target", {})
        if (
            migration.get("status") != "passed"
            or source_cleanup.get("database_absent") is not True
            or source_cleanup.get("slot_absent") is not True
            or target_cleanup.get("database_absent") is not True
            or target_cleanup.get("subscription_absent") is not True
            or migration.get("safety", {}).get(
                "persistent_cluster_configuration_change"
            )
            is not False
        ):
            raise ExerciseError("migration experiment or exact cleanup did not pass")
    finally:
        if re.fullmatch(r"/tmp/pg36-ch29\.[0-9a-f]{32}", remote_root):
            completed = run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    target,
                    "rm",
                    "-rf",
                    "--",
                    remote_root,
                ],
                check=False,
            )
            probe = run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    target,
                    "test",
                    "!",
                    "-e",
                    remote_root,
                ],
                check=False,
            )
            cleanup_verified = completed.returncode == 0 and probe.returncode == 0
        cleanup = {
            "schema": "pg36-ch29-remote-cleanup-v1",
            "captured_at": utc_now(),
            "remote_path": remote_root,
            "experiment_return_code": experiment_return_code,
            "remote_temp_absent": cleanup_verified,
        }
        cleanup_path = evidence_dir / "remote-cleanup.json"
        cleanup_path.write_text(
            json.dumps(cleanup, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cleanup_path.chmod(0o600)
    if not cleanup_verified:
        raise ExerciseError("remote temporary cleanup verification failed")
    print(
        json.dumps(
            {
                "status": "exercise-ok",
                "remote_temp_absent": True,
                "two_cluster_fixture_absent": True,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ExerciseError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(f"chapter 29 exercise failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
