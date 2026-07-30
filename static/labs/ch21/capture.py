#!/usr/bin/env python3
"""Capture a read-only chapter 21 backup/recovery readiness snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import (
    LabError,
    patroni_list,
    pgbackrest_info,
    read_json,
    require_stable_source,
    sanitized_repo_info,
    source_sql_state,
    utc_now,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        target = requirements["target"]
        topology = patroni_list(
            args.ssh_user,
            str(target["source_address"]),
        )
        require_stable_source(topology, requirements)
        source, _raw_system_identifier = source_sql_state(
            args.ssh_user,
            str(target["source_address"]),
        )
        repository = sanitized_repo_info(
            pgbackrest_info(
                args.ssh_user,
                str(target["source_address"]),
                str(requirements["repository"]["stanza"]),
            )
        )
        write_json(
            args.output,
            {
                "schema": "pg36-ch21-current-snapshot-v1",
                "release": requirements["release"],
                "captured_at": utc_now(),
                "target": target["id"],
                "mutation": "none",
                "secret_values_exported": 0,
                "source_system_identifier_recorded": False,
                "patroni": topology,
                "postgres": source,
                "repository": repository,
                "decision": {
                    "sandbox_readiness": "observed",
                    "recoverability": "not-proven-by-capture",
                    "production_ch21_gate": "pending",
                },
            },
        )
    except (LabError, KeyError, TypeError, OSError) as error:
        sys.stderr.write(f"capture failed: {error}\n")
        return 1
    print("status=capture-ok")
    print("mutation=none")
    print("secret_values_exported=0")
    print(f"evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
