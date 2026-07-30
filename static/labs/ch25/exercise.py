#!/usr/bin/env python3
"""Run chapter 25 rules and routes in an isolated sandbox workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


UPLOAD_NAMES = [
    "recording-rules.yml",
    "alert-rules.yml",
    "rule-tests.yml",
    "alertmanager-sandbox.yml",
]

MATCHER_RE = re.compile(
    r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"\s*$'
)


class ExerciseError(RuntimeError):
    """Raised when an isolated rule or route test fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    return parser.parse_args()


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 60.0,
) -> str:
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        stderr = str(getattr(exc, "stderr", "")).strip()
        stdout = str(getattr(exc, "stdout", "")).strip()
        detail = stderr or stdout or str(exc)
        raise ExerciseError(
            f"command failed ({command[0]}): {detail}"
        ) from exc
    return completed.stdout.strip()


def ssh_base(ssh_user: str, bastion: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        f"{ssh_user}@{bastion}",
    ]


def validate_remote_tmp(path: str) -> None:
    if not re.fullmatch(r"/tmp/pg36-ch25\.[A-Za-z0-9]+", path):
        raise ExerciseError(f"unexpected remote temp path: {path}")


def matcher_matches(matcher: str, labels: dict[str, str]) -> bool:
    parsed = MATCHER_RE.match(matcher)
    if not parsed:
        raise ExerciseError(f"unsupported matcher: {matcher}")
    key, operator, expected = parsed.groups()
    actual = str(labels.get(key, ""))
    if operator == "=":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == "=~":
        return re.fullmatch(expected, actual) is not None
    return re.fullmatch(expected, actual) is None


def match_all(matchers: Any, labels: dict[str, str]) -> bool:
    return isinstance(matchers, list) and all(
        matcher_matches(str(matcher), labels) for matcher in matchers
    )


def inhibited(
    config: dict[str, Any],
    source: dict[str, str],
    target: dict[str, str],
) -> bool:
    for rule in config.get("inhibit_rules", []):
        if not match_all(rule.get("source_matchers", []), source):
            continue
        if not match_all(rule.get("target_matchers", []), target):
            continue
        if all(
            source.get(key) == target.get(key)
            for key in rule.get("equal", [])
        ):
            return True
    return False


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    args = parse_args()
    remote_tmp: str | None = None
    cleanup_ok = False
    lines: list[str] = []
    remote = ssh_base(args.ssh_user, args.bastion)
    try:
        routes = json.loads(
            (args.source_dir / "route-tests.json").read_text(
                encoding="utf-8"
            )
        )
        alertmanager = yaml.safe_load(
            (args.source_dir / "alertmanager-sandbox.yml").read_text(
                encoding="utf-8"
            )
        )
        if (
            routes.get("real_receiver") is not False
            or routes.get("live_alertmanager_used") is not False
        ):
            raise ExerciseError(
                "route exercise attempted a real receiver or live endpoint"
            )
        remote_tmp = run(
            remote + ["mktemp", "-d", "/tmp/pg36-ch25.XXXXXXXX"]
        )
        validate_remote_tmp(remote_tmp)
        scp = [
            "scp",
            "-q",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            *[str(args.source_dir / name) for name in UPLOAD_NAMES],
            f"{args.ssh_user}@{args.bastion}:{remote_tmp}/",
        ]
        run(scp)

        run(
            remote
            + [
                "/usr/bin/vmalert",
                f"-rule={remote_tmp}/recording-rules.yml",
                f"-rule={remote_tmp}/alert-rules.yml",
                "-dryRun",
            ],
            timeout=30.0,
        )
        lines.append("vmalert_dry_run=ok")

        run(
            remote
            + [
                "/usr/bin/vmalert-tool",
                "unittest",
                f"--files={remote_tmp}/rule-tests.yml",
            ],
            timeout=120.0,
        )
        lines.append("vmalert_unit_tests=ok")

        run(
            remote
            + [
                "/usr/bin/amtool",
                "check-config",
                f"{remote_tmp}/alertmanager-sandbox.yml",
            ]
        )
        lines.append("alertmanager_config=ok")

        route_count = 0
        for test in routes.get("tests", []):
            expected = test.get("expected_receivers", [])
            if len(expected) != 1:
                raise ExerciseError(
                    f"route test must expect one sink: {test.get('id')}"
                )
            labels = [
                f"{key}={value}"
                for key, value in test.get("labels", {}).items()
            ]
            output = run(
                remote
                + [
                    "/usr/bin/amtool",
                    "config",
                    "routes",
                    "test",
                    f"--config.file={remote_tmp}/alertmanager-sandbox.yml",
                    f"--verify.receivers={expected[0]}",
                    *labels,
                ]
            )
            if expected[0] not in output.splitlines():
                raise ExerciseError(
                    f"route output did not contain sink: {test.get('id')}"
                )
            route_count += 1
        lines.append(f"route_tests={route_count}-ok")

        inhibition_count = 0
        for test in routes.get("inhibition_tests", []):
            actual = inhibited(
                alertmanager,
                {
                    str(key): str(value)
                    for key, value in test.get("source", {}).items()
                },
                {
                    str(key): str(value)
                    for key, value in test.get("target", {}).items()
                },
            )
            if actual is not test.get("expected_inhibited"):
                raise ExerciseError(
                    f"inhibition mismatch: {test.get('id')}"
                )
            inhibition_count += 1
        lines.append(f"inhibition_tests={inhibition_count}-ok")
        lines.append("real_receiver=false")
        lines.append("live_alertmanager_used=false")
        lines.append("live_rule_deployment=false")
        lines.append("live_alert_submission=false")
        lines.append("database_mutation=none")
    except (
        ExerciseError,
        OSError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
        print(f"exercise failed: {exc}", file=sys.stderr)
        return_code = 1
    else:
        return_code = 0
    finally:
        if remote_tmp is not None:
            try:
                validate_remote_tmp(remote_tmp)
                cleanup_script = r"""
set -Eeuo pipefail
target="$1"
case "$target" in
  /tmp/pg36-ch25.[A-Za-z0-9]*)
    rm -rf -- "$target"
    [[ ! -e "$target" ]]
    printf 'cleanup-ok\n'
    ;;
  *)
    exit 70
    ;;
esac
"""
                cleanup_output = run(
                    remote + ["/bin/bash", "-s", "--", remote_tmp],
                    input_text=cleanup_script,
                )
                if cleanup_output != "cleanup-ok":
                    raise ExerciseError(
                        "remote cleanup did not return its proof token"
                    )
                cleanup_ok = True
            except ExerciseError as cleanup_exc:
                print(
                    f"exercise cleanup failed: {cleanup_exc}",
                    file=sys.stderr,
                )
                return_code = 1
        lines.append(
            "remote_cleanup=ok" if cleanup_ok else "remote_cleanup=failed"
        )
        write_private(args.output, "\n".join(lines) + "\n")
    if return_code == 0:
        print("status=exercise-ok")
        print(f"output={args.output}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
