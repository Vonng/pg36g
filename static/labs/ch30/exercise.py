#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExerciseError(RuntimeError):
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_hashes(source_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(source_dir / name)
        for name in SOURCE_FILES
    }


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env={
            **os.environ,
            "LC_ALL": "C",
            "LANG": "C",
            "PAGER": "cat",
        },
    )
    if check and completed.returncode != 0:
        raise ExerciseError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(command[:3])}\n{completed.stderr[-4000:]}"
        )
    return completed


def create_remote_root(target: str, remote_root: str, run_id: str) -> None:
    script = textwrap.dedent(
        """
        import json
        import os
        import sys
        from pathlib import Path

        root = Path(sys.argv[1])
        run_id = sys.argv[2]
        if (
            root.parent != Path("/tmp")
            or not root.name.startswith("pg36-ch30-remote-")
            or root.exists()
            or run_id not in root.name
        ):
            raise SystemExit("unsafe remote root")
        root.mkdir(mode=0o700)
        marker = root / "marker.json"
        marker.write_text(
            json.dumps(
                {
                    "schema": "pg36-ch30-remote-marker-v1",
                    "run_id": run_id,
                },
                sort_keys=True,
            )
            + "\\n"
        )
        marker.chmod(0o600)
        print(json.dumps({"created": str(root), "run_id": run_id}))
        """
    )
    run(
        ["ssh", "-o", "BatchMode=yes", target, "python3", "-", remote_root, run_id],
        input_text=script,
        timeout=30,
    )


def copy_remote_evidence(
    target: str,
    remote_root: str,
    evidence_dir: Path,
) -> None:
    remote_dir = evidence_dir / "remote"
    if remote_dir.exists():
        raise ExerciseError(f"remote evidence destination exists: {remote_dir}")
    completed = run(
        [
            "scp",
            "-q",
            "-r",
            f"{target}:{remote_root}/evidence",
            str(remote_dir),
        ],
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise ExerciseError(
            f"could not copy remote evidence: {completed.stderr[-3000:]}"
        )
    for path in remote_dir.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)


def cleanup_remote_root(
    target: str,
    remote_root: str,
    run_id: str,
) -> dict[str, Any]:
    script = textwrap.dedent(
        """
        import json
        import os
        import shutil
        import sys
        from pathlib import Path

        root = Path(sys.argv[1])
        run_id = sys.argv[2]
        if (
            root.parent != Path("/tmp")
            or not root.name.startswith("pg36-ch30-remote-")
            or run_id not in root.name
        ):
            raise SystemExit("unsafe cleanup root")
        marker = root / "marker.json"
        value = json.loads(marker.read_text())
        if (
            value.get("schema") != "pg36-ch30-remote-marker-v1"
            or value.get("run_id") != run_id
        ):
            raise SystemExit("remote marker mismatch")

        active = []
        for pidfile in root.rglob("postmaster.pid"):
            try:
                pid = int(pidfile.read_text().splitlines()[0])
                os.kill(pid, 0)
                active.append({"pid": pid, "pidfile": str(pidfile)})
            except (
                FileNotFoundError,
                IndexError,
                ValueError,
                ProcessLookupError,
                PermissionError,
            ):
                pass
        if active:
            raise SystemExit(
                "temporary postmaster still active: " + json.dumps(active)
            )
        shutil.rmtree(root)
        print(
            json.dumps(
                {
                    "remote_root_absent": not root.exists(),
                    "active_postmasters": active,
                },
                sort_keys=True,
            )
        )
        """
    )
    completed = run(
        ["ssh", "-o", "BatchMode=yes", target, "python3", "-", remote_root, run_id],
        input_text=script,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ExerciseError(
            f"remote cleanup failed: {completed.stderr[-3000:]}"
        )
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--old-bin", required=True, type=Path)
    parser.add_argument("--old-share", required=True, type=Path)
    parser.add_argument("--new-bin", required=True, type=Path)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    evidence_dir = args.evidence_dir.resolve()
    preflight_path = evidence_dir / "preflight-evidence.json"
    if not preflight_path.is_file():
        raise ExerciseError(f"preflight evidence missing: {preflight_path}")
    preflight = json.loads(preflight_path.read_text())
    if preflight.get("schema") != "pg36-ch30-preflight-evidence-v1":
        raise ExerciseError("preflight schema mismatch")
    hashes = current_hashes(source_dir)
    if hashes != preflight.get("source_hashes"):
        raise ExerciseError("lab source changed after preflight capture")

    recorded_paths = preflight["environment"]["paths"]
    if (
        str(args.old_bin) != recorded_paths["old_bin"]
        or str(args.old_share) != recorded_paths["old_share"]
        or str(args.new_bin) != recorded_paths["new_bin"]
    ):
        raise ExerciseError("binary paths changed after preflight")

    run_id = str(uuid.uuid4())
    target = f"{args.ssh_user}@{args.bastion}"
    remote_root = f"/tmp/pg36-ch30-remote-{run_id}"
    remote_created = False
    evidence_copied = False
    command_error: ExerciseError | None = None

    try:
        create_remote_root(target, remote_root, run_id)
        remote_created = True
        run(
            [
                "scp",
                "-q",
                str(source_dir / "remote_experiment.py"),
                str(source_dir / "requirements.json"),
                str(source_dir / "upgrade-contract.json"),
                f"{target}:{remote_root}/",
            ],
            timeout=60,
        )
        completed = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                target,
                "python3",
                f"{remote_root}/remote_experiment.py",
                "--requirements",
                f"{remote_root}/requirements.json",
                "--contract",
                f"{remote_root}/upgrade-contract.json",
                "--marker-file",
                f"{remote_root}/marker.json",
                "--run-root",
                f"{remote_root}/run",
                "--output-dir",
                f"{remote_root}/evidence",
                "--run-id",
                run_id,
                "--preflight-run-id",
                preflight["preflight_run_id"],
                "--old-bin",
                str(args.old_bin),
                "--old-share",
                str(args.old_share),
                "--new-bin",
                str(args.new_bin),
            ],
            check=False,
            timeout=600,
        )
        write_path = evidence_dir / "remote-command.log"
        write_path.write_text(completed.stdout + completed.stderr)
        write_path.chmod(0o600)
        if completed.returncode != 0:
            command_error = ExerciseError(
                "remote experiment failed; see remote-command.log"
            )
        copy_remote_evidence(target, remote_root, evidence_dir)
        evidence_copied = True
        if command_error is not None:
            raise command_error

        migration = json.loads(
            (
                evidence_dir
                / "remote"
                / "upgrade-evidence.json"
            ).read_text()
        )
        fixture_cleanup = json.loads(
            (
                evidence_dir
                / "remote"
                / "fixture-cleanup.json"
            ).read_text()
        )
        if (
            migration.get("run_id") != run_id
            or migration.get("preflight_run_id")
            != preflight["preflight_run_id"]
            or fixture_cleanup.get("run_id") != run_id
            or fixture_cleanup.get("run_root_absent") is not True
        ):
            raise ExerciseError("remote evidence identity mismatch")
    finally:
        cleanup_result: dict[str, Any] | None = None
        if remote_created:
            cleanup_result = cleanup_remote_root(
                target, remote_root, run_id
            )
        if cleanup_result is not None:
            cleanup = {
                "schema": "pg36-ch30-remote-cleanup-v1",
                "run_id": run_id,
                "captured_at": utc_now(),
                "remote_root_absent":
                    cleanup_result["remote_root_absent"],
                "active_postmasters":
                    cleanup_result["active_postmasters"],
                "remote_evidence_copied": evidence_copied,
                "unrelated_processes_terminated": 0,
            }
            cleanup_path = evidence_dir / "remote-cleanup.json"
            cleanup_path.write_text(
                json.dumps(cleanup, indent=2, sort_keys=True) + "\n"
            )
            cleanup_path.chmod(0o600)

    print(
        json.dumps(
            {
                "status": "exercise-ok",
                "run_id": run_id,
                "preflight_run_id": preflight["preflight_run_id"],
                "upgrade_method": "copy",
                "temporary_cleanup": "verified",
                "production_ch30_gate": "pending",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    try:
        raise SystemExit(main())
    except ExerciseError as exc:
        print(f"exercise failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
