#!/usr/bin/env python3
"""Review a chapter 19 L2 sandbox evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_NEGATIVE_CODES = {
    "claim-production-slo-from-sandbox": "E_PRODUCTION_CLAIM",
    "reuse-one-machine-identity": "E_HOST_IDENTITY",
    "mix-host-operating-systems": "E_HOST_UNIFORMITY",
    "accept-unsynchronized-clock": "E_CLOCK",
    "accept-memory-below-floor": "E_RESOURCE_FLOOR",
    "disable-data-checksums": "E_PG_INIT",
    "declare-two-live-leaders": "E_TOPOLOGY",
    "export-from-world-readable-inventory": "E_SECRET_FILE_MODE",
    "export-one-secret-value": "E_SECRET_EXPORT",
}

EXPECTED_EXCEPTIONS = [
    "EX19-SHARED-HYPERVISOR",
    "EX19-SINGLE-ETCD",
    "EX19-SINGLE-BACKUP-TARGET",
    "EX19-VIRTUAL-STORAGE",
    "EX19-INVENTORY-SECRETS",
    "EX19-LAB-RESOURCE-FLOOR",
]


class ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_hosts(requirements: dict[str, Any]) -> list[str]:
    return sorted(
        str(member["address"])
        for unit in requirements["service_units"]
        for member in unit["members"]
    )


def review_source_identity(
    evidence: Path,
    source: Path,
    requirements: dict[str, Any],
    baseline: dict[str, Any],
) -> None:
    manifest = load_json(evidence / "capture-manifest.json")
    require(
        manifest.get("schema") == "pg36-ch19-capture-manifest-v1"
        and manifest.get("target") == "pg36-l2-vagrant"
        and manifest.get("mode") == "read-only-ssh-sql-rest-tcp"
        and manifest.get("production_approval") is False,
        "capture manifest identity or authority drifted",
    )
    captured = manifest.get("source_sha256", {})
    actual = {
        path.name: sha256(path)
        for path in sorted(source.iterdir())
        if path.is_file()
    }
    require(captured == actual, "captured source checksums do not match review source")

    positive = load_json(evidence / "validation-report.json")
    checksums = positive.get("canonical_sha256", {})
    require(
        checksums.get("requirements") == canonical_sha256(requirements)
        and checksums.get("baseline") == canonical_sha256(baseline),
        "validation report was produced from different decision documents",
    )


def review_positive(
    evidence: Path,
    requirements: dict[str, Any],
) -> None:
    report = load_json(evidence / "validation-report.json")
    require(
        report.get("schema") == "pg36-ch19-validation-report-v1"
        and report.get("release") == "2.0-sandbox"
        and report.get("status") == "ok",
        "normal validation report identity drifted",
    )
    require(
        report.get("decision")
        == {
            "sandbox_l2": "accepted-with-exceptions",
            "production_ch19_gate": "pending",
            "next_gate": "ch20-ha",
        },
        "validation decision crossed its interpretation boundary",
    )
    require(
        report.get("counts")
        == {
            "hosts": 4,
            "postgresql_members": 4,
            "postgresql_clusters": 2,
            "service_units": 2,
            "accepted_exceptions": 6,
        },
        "accepted topology or exception counts drifted",
    )
    facts = report.get("facts", {})
    system_ids = facts.get("system_identifiers", {})
    require(
        facts.get("pigsty_version") == "v4.4.0"
        and facts.get("postgresql_major") == 18
        and facts.get("host_os") == "24.04"
        and facts.get("host_architecture") == "aarch64"
        and set(system_ids) == {"pg-meta", "pg-test"}
        and all(str(value).isdigit() for value in system_ids.values())
        and len(set(system_ids.values())) == 2,
        "accepted implementation facts drifted",
    )
    require(
        report.get("accepted_exception_ids") == EXPECTED_EXCEPTIONS
        and report.get("accepted_exception_ids")
        == [
            row["id"]
            for row in requirements["accepted_sandbox_exceptions"]
        ],
        "accepted exception set drifted",
    )


def review_negative(evidence: Path) -> None:
    report = load_json(evidence / "negative-report.json")
    require(
        report.get("schema") == "pg36-ch19-negative-report-v1"
        and report.get("release") == "2.0-sandbox"
        and report.get("status") == "ok"
        and report.get("case_count") == len(EXPECTED_NEGATIVE_CODES),
        "negative report identity drifted",
    )
    actual = {
        row["id"]: row["actual_code"]
        for row in report.get("cases", [])
    }
    expected = {
        row["id"]: row["expected_code"]
        for row in report.get("cases", [])
    }
    require(
        actual == EXPECTED_NEGATIVE_CODES
        and expected == EXPECTED_NEGATIVE_CODES,
        "counterexamples were not rejected by their intended policy codes",
    )


def review_live_evidence(
    evidence: Path,
    requirements: dict[str, Any],
) -> None:
    hosts = expected_hosts(requirements)
    inventory = load_json(evidence / "inventory-projection.json")
    require(
        inventory.get("status") == "secret-free-projection"
        and inventory.get("source", {}).get("mode_octal") == "0600"
        and inventory.get("source", {}).get("content_fingerprint")
        == "withheld-secret-bearing-source"
        and "sha256" not in inventory.get("source", {})
        and inventory.get("source", {}).get("secret_values_exported") == 0
        and inventory.get("hosts") == hosts,
        "inventory evidence leaked authority or changed target",
    )

    identities: list[str] = []
    below_recommendation: list[str] = []
    contract = requirements["host_contract"]
    for host in hosts:
        fact = load_json(evidence / "hosts" / f"{host}.json")
        identities.append(str(fact.get("machine_id_sha256", "")))
        if (
            fact.get("cpu", {}).get("logical_count", 0)
            < contract["recommended_minimum_cpu_count"]
            or fact.get("memory", {}).get("total_bytes", 0)
            < contract["recommended_minimum_memory_bytes"]
        ):
            below_recommendation.append(host)
    require(
        all(len(identity) == 64 for identity in identities)
        and len(set(identities)) == 4,
        "machine identity evidence is missing or duplicated",
    )
    require(
        below_recommendation == ["10.10.10.11", "10.10.10.12", "10.10.10.13"],
        "resource-floor exception no longer describes the observed guests",
    )

    endpoints = load_json(evidence / "endpoints.json")
    for host in hosts:
        row = endpoints.get("hosts", {}).get(host, {})
        require(
            all(row.get("tcp", {}).values())
            and row.get("patroni", {}).get("reachable") is True,
            f"endpoint evidence is incomplete for {host}",
        )


def review_deployment_account(source: Path) -> None:
    account = load_json(source / "deployment-run.json")
    recap = account.get("execution", {}).get("recap", {})
    require(
        account.get("schema") == "pg36-ch19-deployment-run-v1"
        and account.get("release") == "2.0-sandbox"
        and account.get("source", {}).get("pigsty_release") == "v4.4.0"
        and account.get("source", {}).get("local_dirty_worktree_used") is False
        and account.get("execution", {}).get("return_code") == 0
        and set(recap)
        == {
            "10.10.10.10",
            "10.10.10.11",
            "10.10.10.12",
            "10.10.10.13",
            "localhost",
        }
        and all(
            row.get("failed") == 0 and row.get("unreachable") == 0
            for row in recap.values()
        )
        and account.get("boundary", {}).get("reset_executed") is False,
        "sanitized deployment account drifted",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = load_json(args.source_dir / "requirements.json")
        baseline = load_json(args.source_dir / "baseline-v2.0-sandbox.json")
        review_source_identity(
            args.evidence,
            args.source_dir,
            requirements,
            baseline,
        )
        review_positive(args.evidence, requirements)
        review_negative(args.evidence)
        review_live_evidence(args.evidence, requirements)
        review_deployment_account(args.source_dir)
    except (ReviewError, KeyError, TypeError) as error:
        sys.stderr.write(f"review failed: {error}\n")
        return 1
    print("status=ok")
    print("target=pg36-l2-vagrant")
    print("deployment=pigsty-v4.4.0-postgresql-18")
    print("hosts=4-distinct")
    print("topology=pg-meta-1-primary+pg-test-1-primary-2-replicas")
    print("counterexamples=9-rejected")
    print("sandbox_l2=accepted-with-exceptions")
    print("production_ch19_gate=pending")
    print("mutation=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
