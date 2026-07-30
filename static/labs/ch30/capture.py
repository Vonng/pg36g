#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaptureError(RuntimeError):
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


def source_hashes(source_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file():
            raise CaptureError(f"source file missing: {path}")
        result[name] = sha256_file(path)
    return result


def remote_probe(
    *,
    ssh_user: str,
    bastion: str,
    old_bin: Path,
    old_share: Path,
    new_bin: Path,
    service: str,
) -> dict[str, Any]:
    script = textwrap.dedent(
        r'''
        import hashlib
        import json
        import os
        import platform
        import shutil
        import subprocess
        import sys
        from pathlib import Path

        old_bin = Path(sys.argv[1]).resolve()
        old_share = Path(sys.argv[2]).resolve()
        new_bin = Path(sys.argv[3]).resolve()
        service = sys.argv[4]

        def command(args, *, input_text=None):
            completed = subprocess.run(
                args,
                input=input_text,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                env={
                    **os.environ,
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PAGER": "cat",
                    "PSQL_PAGER": "cat",
                    "PGCONNECT_TIMEOUT": "5",
                },
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"command failed: {args[:2]}: {completed.stderr[-2000:]}"
                )
            return completed.stdout.strip()

        def sha(path):
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        required = [
            old_bin / "postgres",
            old_bin / "initdb",
            old_bin / "pg_ctl",
            old_bin / "psql",
            old_bin / "pg_checksums",
            old_share / "postgres.bki",
            new_bin / "postgres",
            new_bin / "initdb",
            new_bin / "pg_upgrade",
            new_bin / "vacuumdb",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise RuntimeError("required files missing: " + ", ".join(missing))

        host = json.loads(
            command(
                [
                    "psql",
                    "-X",
                    "-w",
                    "-A",
                    "-t",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "--no-psqlrc",
                    "-d",
                    f"service={service} dbname=postgres "
                    "application_name=pg36-ch30-preflight",
                    "-c",
                    """
                    SELECT jsonb_build_object(
                      'cluster_name', current_setting('cluster_name'),
                      'server_version', current_setting('server_version'),
                      'server_version_num',
                        current_setting('server_version_num')::int,
                      'system_identifier',
                        (SELECT system_identifier FROM pg_control_system()),
                      'in_recovery', pg_is_in_recovery(),
                      'data_checksums',
                        current_setting('data_checksums')
                    );
                    """,
                ]
            )
        )

        locale_output = command(["locale", "-a"]).splitlines()
        stale_roots = sorted(
            str(path)
            for path in Path("/tmp").glob("pg36-ch30-remote-*")
            if path.exists()
        )
        live_temp_postmasters = []
        proc_root = Path("/proc")
        if proc_root.is_dir():
            for proc in proc_root.iterdir():
                if not proc.name.isdigit():
                    continue
                try:
                    raw = (proc / "cmdline").read_bytes()
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
                text = raw.replace(b"\x00", b" ").decode(
                    "utf-8", errors="replace"
                )
                if "postgres" in text and "pg36-ch30-remote-" in text:
                    live_temp_postmasters.append(
                        {"pid": int(proc.name), "command": text[:500]}
                    )

        disk = shutil.disk_usage("/tmp")
        print(
            json.dumps(
                {
                    "architecture": platform.machine(),
                    "old_postgresql": command(
                        [str(old_bin / "postgres"), "--version"]
                    ),
                    "new_postgresql": command(
                        [str(new_bin / "postgres"), "--version"]
                    ),
                    "old_postgres_sha256": sha(old_bin / "postgres"),
                    "old_initdb_sha256": sha(old_bin / "initdb"),
                    "old_share_postgres_bki_sha256": sha(
                        old_share / "postgres.bki"
                    ),
                    "new_postgres_sha256": sha(new_bin / "postgres"),
                    "new_pg_upgrade_sha256": sha(
                        new_bin / "pg_upgrade"
                    ),
                    "locale_c_available": "C" in locale_output,
                    "locale_c_utf8_available": any(
                        value.lower() in {"c.utf8", "c.utf-8"}
                        for value in locale_output
                    ),
                    "tmp_total_bytes": disk.total,
                    "tmp_free_bytes": disk.free,
                    "stale_fixture_roots": stale_roots,
                    "live_temp_postmasters": live_temp_postmasters,
                    "managed_host": host,
                    "paths": {
                        "old_bin": str(old_bin),
                        "old_share": str(old_share),
                        "new_bin": str(new_bin),
                    },
                },
                sort_keys=True,
            )
        )
        '''
    )
    target = f"{ssh_user}@{bastion}"
    completed = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            target,
            "python3",
            "-",
            str(old_bin),
            str(old_share),
            str(new_bin),
            service,
        ],
        input=script,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise CaptureError(
            f"remote preflight failed: {completed.stderr[-3000:]}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CaptureError(
            f"remote preflight was not JSON: {completed.stdout[-2000:]}"
        ) from exc


def parse_major(version: str) -> int:
    for token in version.replace("(", " ").replace(")", " ").split():
        if token and token[0].isdigit():
            return int(token.split(".", 1)[0])
    raise CaptureError(f"cannot parse version: {version}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--upstream-root", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--old-bin", required=True, type=Path)
    parser.add_argument("--old-share", required=True, type=Path)
    parser.add_argument("--new-bin", required=True, type=Path)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    requirements = json.loads(args.requirements.read_text())
    contract = json.loads(args.contract.read_text())
    if (
        requirements.get("schema") != "pg36-ch30-requirements-v1"
        or contract.get("schema") != "pg36-ch30-upgrade-contract-v1"
    ):
        raise CaptureError("static contracts have unexpected schemas")

    hashes = source_hashes(source_dir)
    upstream: dict[str, Any] = {}
    for name, relative in requirements["upstream"].items():
        path = (source_dir / relative).resolve()
        if upstream_root not in path.parents:
            raise CaptureError(f"upstream path escapes lab root: {path}")
        if not path.is_file():
            raise CaptureError(f"upstream evidence missing: {path}")
        upstream[name] = {
            "relative_path": str(path.relative_to(upstream_root)),
            "sha256": sha256_file(path),
        }

    remote = remote_probe(
        ssh_user=args.ssh_user,
        bastion=args.bastion,
        old_bin=args.old_bin,
        old_share=args.old_share,
        new_bin=args.new_bin,
        service=requirements["host"]["service"],
    )
    if (
        parse_major(remote["old_postgresql"])
        != requirements["versions"]["old_major"]
        or parse_major(remote["new_postgresql"])
        != requirements["versions"]["new_major"]
        or remote["managed_host"].get("cluster_name")
        != requirements["host"]["cluster"]
        or remote["managed_host"].get("in_recovery") is not False
        or remote["locale_c_available"] is not True
        or int(remote["tmp_free_bytes"])
        < int(requirements["execution"]["minimum_free_bytes"])
        or remote["stale_fixture_roots"]
        or remote["live_temp_postmasters"]
    ):
        raise CaptureError("remote environment does not satisfy requirements")

    evidence = {
        "schema": "pg36-ch30-preflight-evidence-v1",
        "preflight_run_id": str(uuid.uuid4()),
        "captured_at": utc_now(),
        "target": requirements["target"],
        "environment": {
            **remote,
            "old_major": parse_major(remote["old_postgresql"]),
            "new_major": parse_major(remote["new_postgresql"]),
        },
        "source_hashes": hashes,
        "upstream": upstream,
        "risk": {
            "mutation": "none",
            "production_data_touched": False,
            "production_traffic_touched": False,
            "pigsty_inventory_changed": False,
            "patroni_configuration_changed": False,
            "persistent_cluster_configuration_change": False,
            "system_package_changed": False,
        },
        "decision": {
            "capture": "pass",
            "exercise_authorized_scope":
                "private-temporary-clusters-only",
            "production_ch30_gate": "pending",
        },
    }
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    args.output.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "capture-ok",
                "preflight_run_id": evidence["preflight_run_id"],
                "old_postgresql": remote["old_postgresql"],
                "new_postgresql": remote["new_postgresql"],
                "source_files_hash_bound": len(hashes),
                "production_ch30_gate": "pending",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
