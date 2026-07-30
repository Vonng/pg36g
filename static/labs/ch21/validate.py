#!/usr/bin/env python3
"""Validate chapter 21 positive evidence and adversarial counterexamples."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from common import LabError, read_json, write_json


class PolicyError(LabError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def reject(condition: bool, code: str, message: str) -> None:
    if condition:
        raise PolicyError(code, message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_bundle(root: Path) -> dict[str, Any]:
    names = {
        "manifest": "drill-manifest.json",
        "before": "source-before.json",
        "fixture": "fixture.json",
        "backup": "backup.json",
        "recovery": "recovery.json",
        "shutdown": "isolated-shutdown.json",
        "after": "source-after.json",
    }
    return {key: read_json(root / name) for key, name in names.items()}


def member_index(phase: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = phase.get("patroni", {}).get("members", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }


def validate_source_phase(
    phase: dict[str, Any],
    requirements: dict[str, Any],
    *,
    after: bool,
) -> None:
    expected = requirements["source_acceptance"]
    members = member_index(phase)
    reject(
        set(members) != set(expected["members"]),
        "E_SOURCE_HEALTH",
        "source member set drifted",
    )
    leaders = [
        name
        for name, row in members.items()
        if row.get("role") in {"primary", "leader"}
    ]
    reject(
        leaders != [expected["initial_leader"]],
        "E_SOURCE_HEALTH",
        "source leader drifted",
    )
    for name, row in members.items():
        expected_state = (
            "running"
            if name == expected["initial_leader"]
            else "streaming"
        )
        reject(
            row.get("state") != expected_state,
            "E_SOURCE_HEALTH",
            f"source member {name} is not {expected_state}",
        )
        lag = row.get("replay_lag_bytes")
        reject(
            isinstance(lag, int)
            and lag > expected["maximum_replay_lag_bytes"],
            "E_SOURCE_HEALTH",
            f"source member {name} exceeds lag policy",
        )
    postgres = phase.get("postgres", {})
    reject(
        postgres.get("in_recovery") is not False,
        "E_SOURCE_HEALTH",
        "declared source primary is not writable",
    )
    if after:
        live = phase.get("restore_host_live_member", {})
        reject(
            live.get("in_recovery") is not True
            or live.get("wal_replay_paused") is not False
            or live.get("cluster_name") != requirements["target"]["cluster"]
            or live.get("port") != 5432,
            "E_SOURCE_HEALTH",
            "restore host no longer serves as the live Patroni replica",
        )
        reject(
            phase.get("source_system_identifier_unchanged") is not True,
            "E_SOURCE_HEALTH",
            "source system identifier changed during the drill",
        )


def validate_ch19_gate(root: Path) -> None:
    for name in ("preflight-ch19", "postflight-ch19"):
        report = read_json(root.parent / name / "validation-report.json")
        reject(
            report.get("schema") != "pg36-ch19-validation-report-v1"
            or report.get("status") != "ok"
            or report.get("decision", {}).get("sandbox_l2")
            != "accepted-with-exceptions",
            "E_SOURCE_HEALTH",
            f"{name} did not pass",
        )


def validate_bundle(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
    evidence_root: Path,
) -> dict[str, Any]:
    manifest = bundle["manifest"]
    before = bundle["before"]
    fixture = bundle["fixture"]
    backup = bundle["backup"]
    recovery = bundle["recovery"]
    shutdown = bundle["shutdown"]
    after = bundle["after"]
    target = requirements["target"]
    restore = requirements["restore"]
    objectives = requirements["objectives"]

    reject(
        manifest.get("production_approval") is not False
        or manifest.get("production_data") is not False
        or manifest.get("production_traffic") is not False,
        "E_PRODUCTION_CLAIM",
        "sandbox evidence cannot carry a production claim",
    )
    reject(
        manifest.get("schema") != "pg36-ch21-drill-manifest-v1"
        or manifest.get("release") != requirements["release"]
        or manifest.get("target") != target["id"]
        or manifest.get("mode")
        != "fresh-full-backup-and-isolated-named-pitr"
        or manifest.get("status") != "completed",
        "E_TARGET",
        "drill identity or target drifted",
    )
    reject(
        manifest.get("destructive_cleanup") is not False
        or manifest.get("restore_root_preexisting") is not False,
        "E_TARGET",
        "drill overwrote or cleaned an unreviewed target",
    )
    reject(
        manifest.get("secret_values_exported") != 0
        or manifest.get("raw_system_identifier_exported") is not False,
        "E_SECRET",
        "evidence exported forbidden sensitive values",
    )

    validate_source_phase(before, requirements, after=False)
    validate_source_phase(after, requirements, after=True)
    validate_ch19_gate(evidence_root)

    reject(
        backup.get("repository_status_code")
        != requirements["repository"]["status_code"]
        or backup.get("repository_status") != "ok",
        "E_REPOSITORY",
        "backup repository status is not ok",
    )
    reject(
        backup.get("type") != "full"
        or backup.get("error") is not False
        or not isinstance(backup.get("label"), str)
        or recovery.get("backup_label") != backup.get("label"),
        "E_BACKUP",
        "fresh full backup identity or status failed",
    )
    reject(
        backup.get("command_ms", float("inf"))
        > objectives["maximum_backup_command_ms"],
        "E_BACKUP",
        "backup command exceeded the sandbox objective",
    )
    target_segment = fixture.get("restore_point", {}).get("wal_segment")
    reject(
        backup.get("target_wal_covered") is not True
        or backup.get("target_wal_segment") != target_segment
        or not isinstance(backup.get("maximum_archived_wal"), str)
        or not isinstance(target_segment, str)
        or backup["maximum_archived_wal"] < target_segment,
        "E_ARCHIVE",
        "archive range does not cover the restore point",
    )

    options = recovery.get("restore_options", {})
    effective = recovery.get("effective_state", {})
    runtime = recovery.get("runtime_isolation", {})
    reject(
        options
        != {
            "type": restore["target_type"],
            "target_action": restore["target_action"],
            "target_timeline": restore["target_timeline"],
            "archive_mode": restore["archive_mode"],
        }
        or effective.get("archive_mode") != "off"
        or effective.get("listen_addresses") != ""
        or effective.get("port") != restore["port"]
        or effective.get("ssl") is not False
        or effective.get("cluster_name") != "pg36-ch21-restore"
        or effective.get("shared_preload_libraries") != ""
        or recovery.get("patroni_managed") is not False
        or runtime.get("tcp_listener") is not False
        or runtime.get("socket_exists") is not True
        or str(runtime.get("socket_mode")).lstrip("0") != "700"
        or runtime.get("socket_owner") != "postgres:postgres"
        or runtime.get("postmaster_pid_exists") is not True,
        "E_ISOLATION",
        "restored postmaster crossed its isolation boundary",
    )

    promoted = recovery.get("promoted_state", {})
    reject(
        promoted.get("in_recovery") is not False
        or promoted.get("transaction_read_only") is not False
        or effective.get("in_recovery") is not False
        or effective.get("transaction_read_only") is not False
        or recovery.get("rollback_write_probe") is not True,
        "E_PROMOTION",
        "read-only availability was mistaken for completed promotion",
    )
    reject(
        recovery.get("restore_copy_ms", float("inf"))
        > objectives["maximum_restore_copy_ms"]
        or recovery.get("start_to_first_connection_ms", float("inf"))
        > objectives["maximum_start_to_read_only_ms"]
        or recovery.get("start_to_promoted_ms", float("inf"))
        > objectives["maximum_start_to_promoted_ms"]
        or recovery.get("start_to_first_connection_ms", -1) < 0
        or recovery.get("start_to_promoted_ms", -1) < 0,
        "E_PROMOTION",
        "restore or recovery timing is invalid",
    )

    boundary = recovery.get("boundary", {})
    reject(
        boundary.get("base_present") is not True
        or boundary.get("keep_present") is not True
        or boundary.get("unexpected_stage_count") != 0,
        "E_BOUNDARY",
        "required recovery markers are missing or unexpected",
    )
    reject(
        boundary.get("discard_present") is not False,
        "E_BOUNDARY",
        "post-target marker was replayed",
    )

    lineage = recovery.get("lineage", {})
    reject(
        lineage.get("system_identifier_relation") != "matches source"
        or lineage.get("raw_identifier_recorded") is not False,
        "E_LINEAGE",
        "physical lineage does not match the source",
    )
    increment = lineage.get("timeline_increment")
    reject(
        not isinstance(increment, int)
        or increment < objectives["minimum_new_timeline_increment"]
        or lineage.get("restored_timeline", 0)
        <= lineage.get("source_timeline", 0),
        "E_TIMELINE",
        "PITR did not fork onto a newer timeline",
    )

    reject(
        shutdown.get("postmaster_pid_exists") is not False
        or shutdown.get("socket_exists") is not False
        or shutdown.get("tcp_listener") is not False
        or shutdown.get("restore_directory_retained") is not True,
        "E_SHUTDOWN",
        "isolated postmaster was not stopped cleanly",
    )

    expected_exceptions = requirements["required_exception_ids"]
    return {
        "decision": {
            "sandbox_named_pitr": "accepted-with-exceptions",
            "production_ch21_gate": "pending",
            "regional_disaster_recovery": "not-run",
            "restore_directory": "retained-and-stopped",
        },
        "run_id": manifest["run_id"],
        "backup": {
            "label": backup["label"],
            "command_ms": backup["command_ms"],
            "repository_status": backup["repository_status"],
            "target_wal_covered": backup["target_wal_covered"],
        },
        "recovery": {
            "restore_copy_ms": recovery["restore_copy_ms"],
            "start_to_first_connection_ms":
                recovery["start_to_first_connection_ms"],
            "first_connection_in_recovery":
                recovery.get("first_connection_state", {}).get(
                    "in_recovery"
                ),
            "start_to_promoted_ms": recovery["start_to_promoted_ms"],
            "first_connection_to_promoted_ms":
                recovery["first_connection_to_promoted_ms"],
            "boundary": boundary,
            "system_identifier_relation":
                lineage["system_identifier_relation"],
            "source_timeline": lineage["source_timeline"],
            "restored_timeline": lineage["restored_timeline"],
            "timeline_increment": increment,
            "rollback_write_probe": recovery["rollback_write_probe"],
        },
        "accepted_exception_ids": expected_exceptions,
    }


def mutate(
    bundle: dict[str, Any],
    mutation: str,
) -> dict[str, Any]:
    value = copy.deepcopy(bundle)
    if mutation == "production_claim":
        value["manifest"]["production_approval"] = True
    elif mutation == "target_identity":
        value["manifest"]["target"] = "unreviewed/foreign-cluster"
    elif mutation == "repository_status":
        value["backup"]["repository_status_code"] = 1
        value["backup"]["repository_status"] = "error"
    elif mutation == "backup_error":
        value["backup"]["error"] = True
    elif mutation == "archive_gap":
        value["backup"]["target_wal_covered"] = False
    elif mutation == "archive_mode_on":
        value["recovery"]["effective_state"]["archive_mode"] = "on"
    elif mutation == "tcp_listener":
        value["recovery"]["runtime_isolation"]["tcp_listener"] = True
    elif mutation == "still_in_recovery":
        value["recovery"]["promoted_state"]["in_recovery"] = True
    elif mutation == "keep_missing":
        value["recovery"]["boundary"]["keep_present"] = False
    elif mutation == "discard_present":
        value["recovery"]["boundary"]["discard_present"] = True
    elif mutation == "lineage_mismatch":
        value["recovery"]["lineage"][
            "system_identifier_relation"
        ] = "does not match source"
    elif mutation == "timeline_not_advanced":
        lineage = value["recovery"]["lineage"]
        lineage["restored_timeline"] = lineage["source_timeline"]
        lineage["timeline_increment"] = 0
    elif mutation == "restore_not_stopped":
        value["shutdown"]["postmaster_pid_exists"] = True
    elif mutation == "source_degraded":
        value["after"]["patroni"]["members"][1]["state"] = "stopped"
    else:
        raise LabError(f"unknown negative mutation: {mutation}")
    return value


def validate_negative(
    base: dict[str, Any],
    cases: dict[str, Any],
    requirements: dict[str, Any],
    evidence: Path,
) -> dict[str, Any]:
    reject(
        cases.get("schema") != "pg36-ch21-negative-cases-v1",
        "E_CASE",
        "negative case schema drifted",
    )
    results = []
    for case in cases.get("cases", []):
        if not isinstance(case, dict):
            raise LabError("negative case is not an object")
        expected = str(case.get("expected_code"))
        try:
            validate_bundle(
                mutate(base, str(case.get("mutation"))),
                requirements,
                evidence,
            )
        except PolicyError as error:
            actual = error.code
        else:
            actual = "ACCEPTED"
        if actual != expected:
            raise LabError(
                f"negative case {case.get('id')} expected "
                f"{expected}, got {actual}"
            )
        results.append(
            {
                "id": case.get("id"),
                "expected_code": expected,
                "actual_code": actual,
                "status": "rejected-as-designed",
            }
        )
    return {
        "schema": "pg36-ch21-negative-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "case_count": len(results),
        "cases": results,
    }


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        scenarios = read_json(args.scenarios)
        bundle = load_bundle(args.evidence)
        if args.negative_cases:
            result = validate_negative(
                bundle,
                read_json(args.negative_cases),
                requirements,
                args.evidence,
            )
        else:
            result = validate_bundle(bundle, requirements, args.evidence)
            result = {
                "schema": "pg36-ch21-validation-report-v1",
                "release": requirements["release"],
                "status": "ok",
                **result,
                "canonical_sha256": {
                    "requirements": canonical_sha256(requirements),
                    "recovery_scenarios": canonical_sha256(scenarios),
                },
            }
        write_json(args.output, result)
    except (
        LabError,
        PolicyError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
    ) as error:
        code = getattr(error, "code", "E_VALIDATION")
        sys.stderr.write(f"validation failed [{code}]: {error}\n")
        return 1
    print("status=validation-ok")
    if args.negative_cases:
        print(f"counterexamples={result['case_count']}-rejected")
    else:
        print("sandbox_named_pitr=accepted-with-exceptions")
        print("production_ch21_gate=pending")
    print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
