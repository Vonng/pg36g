#!/usr/bin/env python3
"""Validate chapter 19 inventory, host, PostgreSQL, and Pigsty evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class PolicyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code: str, message: str) -> None:
    raise PolicyError(code, message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("E_EVIDENCE", f"cannot read {path}: {exc}")
    if not isinstance(value, dict):
        fail("E_EVIDENCE", f"{path} must contain an object")
    return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_hosts(requirements: dict[str, Any]) -> list[str]:
    try:
        hosts = [
            str(member["address"])
            for unit in requirements["service_units"]
            for member in unit["members"]
        ]
    except (KeyError, TypeError) as exc:
        fail("E_REQUIREMENTS", f"invalid service unit shape: {exc}")
    if len(hosts) != len(set(hosts)):
        fail("E_REQUIREMENTS", "requirements contain duplicate host addresses")
    return hosts


def load_evidence(
    evidence: Path,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    hosts = expected_hosts(requirements)
    return {
        "inventory": read_json(evidence / "inventory-projection.json"),
        "hosts": {
            host: read_json(evidence / "hosts" / f"{host}.json")
            for host in hosts
        },
        "postgres": {
            host: read_json(evidence / "postgres" / f"{host}.json")
            for host in hosts
        },
        "patroni": {
            cluster: read_json(evidence / "patroni" / f"{cluster}.json")
            for cluster in ("pg-meta", "pg-test")
        },
        "endpoints": read_json(evidence / "endpoints.json"),
        "manifest": read_json(evidence / "capture-manifest.json"),
    }


def normalize_role(role: Any) -> str:
    value = str(role or "").strip().lower().replace(" ", "-")
    if value in {"leader", "master", "primary"}:
        return "primary"
    if value in {"replica", "standby", "sync-standby", "standby-leader"}:
        return "replica"
    return value


def validate_document_identity(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
) -> None:
    if requirements.get("schema") != "pg36-ch19-environment-requirements-v1":
        fail("E_SCHEMA", "unexpected requirements schema")
    if baseline.get("schema") != "pg36-ch19-deployment-baseline-v1":
        fail("E_SCHEMA", "unexpected baseline schema")
    if requirements.get("release") != baseline.get("release"):
        fail("E_RELEASE", "requirements and baseline release differ")
    target = requirements.get("target", {})
    if target.get("id") != baseline.get("target", {}).get("id"):
        fail("E_TARGET", "requirements and baseline target differ")
    if target.get("kind") != "disposable-local-linux-sandbox":
        fail("E_TARGET", "chapter 19 formal target must be the disposable sandbox")


def validate_production_boundary(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
) -> None:
    if any(
        unit.get("production_slo_claimed") is not False
        for unit in requirements.get("service_units", [])
    ):
        fail("E_PRODUCTION_CLAIM", "sandbox service unit claimed a production SLO")
    target = baseline.get("target", {})
    if (
        target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or "not-production-approval" not in str(baseline.get("status", ""))
    ):
        fail("E_PRODUCTION_CLAIM", "baseline crossed the sandbox production boundary")
    if not baseline.get("prohibited_claims"):
        fail("E_PRODUCTION_CLAIM", "baseline needs explicit prohibited claims")


def validate_inventory(
    requirements: dict[str, Any],
    inventory: dict[str, Any],
) -> None:
    if (
        inventory.get("schema") != "pg36-ch19-inventory-projection-v1"
        or inventory.get("status") != "secret-free-projection"
    ):
        fail("E_INVENTORY", "inventory projection identity drifted")
    source = inventory.get("source", {})
    if source.get("mode_octal") != "0600":
        fail("E_SECRET_FILE_MODE", "live inventory must be mode 0600")
    if (
        source.get("content_fingerprint") != "withheld-secret-bearing-source"
        or "sha256" in source
    ):
        fail(
            "E_SECRET_EXPORT",
            "secret-bearing inventory fingerprint must not be exported",
        )
    if source.get("secret_values_exported") != 0:
        fail("E_SECRET_EXPORT", "secret values appeared in exported evidence")
    if not isinstance(source.get("secret_fields_redacted"), int) or source.get(
        "secret_fields_redacted"
    ) < 1:
        fail("E_SECRET_EXPORT", "inventory projection did not record redaction")

    hosts = expected_hosts(requirements)
    if inventory.get("hosts") != sorted(hosts) or inventory.get("host_count") != len(
        hosts
    ):
        fail("E_INVENTORY", "inventory host set drifted")
    global_vars = inventory.get("global", {})
    if (
        global_vars.get("version") != requirements["target"]["pigsty_version"]
        or int(global_vars.get("pg_version", -1))
        != requirements["target"]["postgresql_major"]
        or global_vars.get("pg_locale") != "C.UTF-8"
    ):
        fail("E_INVENTORY", "Pigsty/PostgreSQL/locale declaration drifted")
    forbidden_global_keys = {
        key
        for key in global_vars
        if any(token in key.lower() for token in ("password", "secret", "token"))
    }
    if forbidden_global_keys:
        fail("E_SECRET_EXPORT", f"secret keys escaped projection: {forbidden_global_keys}")

    clusters = inventory.get("postgresql_clusters", {})
    expected_units = {
        unit["id"]: {
            member["address"]: {
                "pg_role": member["declared_role"],
                "pg_offline_query": member["offline_query"],
            }
            for member in unit["members"]
        }
        for unit in requirements["service_units"]
    }
    if set(clusters) != set(expected_units):
        fail("E_INVENTORY", "inventory PostgreSQL cluster set drifted")
    for cluster, members in expected_units.items():
        actual_hosts = clusters[cluster].get("hosts", {})
        if set(actual_hosts) != set(members):
            fail("E_INVENTORY", f"inventory members drifted for {cluster}")
        for host, expected in members.items():
            actual = actual_hosts[host]
            if normalize_role(actual.get("pg_role")) != expected["pg_role"]:
                fail("E_INVENTORY", f"declared role drifted for {host}")
            if bool(actual.get("pg_offline_query", False)) != expected["pg_offline_query"]:
                fail("E_INVENTORY", f"offline declaration drifted for {host}")


def validate_hosts(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
    hosts: dict[str, dict[str, Any]],
) -> None:
    contract = requirements["host_contract"]
    expected = expected_hosts(requirements)
    if set(hosts) != set(expected):
        fail("E_HOST_IDENTITY", "host evidence set drifted")
    identities: list[str] = []
    uniform: set[tuple[Any, ...]] = set()
    for address in expected:
        fact = hosts[address]
        if fact.get("schema") != "pg36-ch19-host-facts-v1":
            fail("E_HOST_IDENTITY", f"host schema drifted for {address}")
        if (
            fact.get("target_ip") != address
            or fact.get("hostname")
            != baseline["target"]["expected_hostnames"].get(address)
        ):
            fail("E_HOST_IDENTITY", f"address/hostname identity drifted for {address}")
        identity = fact.get("machine_id_sha256")
        if not isinstance(identity, str) or len(identity) != 64:
            fail("E_HOST_IDENTITY", f"machine identity missing for {address}")
        identities.append(identity)
        os_fact = fact.get("os", {})
        uniform.add(
            (
                fact.get("kernel"),
                os_fact.get("id"),
                os_fact.get("version_id"),
                fact.get("architecture"),
            )
        )
    if len(set(identities)) != len(identities):
        fail("E_HOST_IDENTITY", "two target addresses share a machine identity")
    if len(uniform) != 1:
        fail("E_HOST_UNIFORMITY", "host OS or architecture is heterogeneous")

    for address in expected:
        fact = hosts[address]
        os_fact = fact["os"]
        if (
            fact.get("kernel") != contract["kernel"]
            or os_fact.get("id") != contract["os_id"]
            or not str(os_fact.get("version_id", "")).startswith(
                contract["os_version_prefix"]
            )
            or fact.get("architecture") != contract["architecture"]
        ):
            fail("E_HOST_UNIFORMITY", f"host contract missed on {address}")
        cpu_count = fact.get("cpu", {}).get("logical_count")
        memory = fact.get("memory", {})
        storage = fact.get("storage", {})
        if (
            not isinstance(cpu_count, int)
            or cpu_count < contract["minimum_cpu_count"]
            or memory.get("total_bytes", 0) < contract["minimum_memory_bytes"]
            or storage.get("root_free_bytes", 0)
            < contract["minimum_root_free_bytes"]
        ):
            fail("E_RESOURCE_FLOOR", f"resource floor missed on {address}")
        if memory.get("swap_total_bytes", 0) > contract["swap_bytes_max"]:
            fail("E_RESOURCE_FLOOR", f"swap contract missed on {address}")
        if (
            memory.get("transparent_hugepage_enabled")
            != contract["transparent_hugepage_enabled"]
        ):
            fail("E_HOST_TUNING", f"THP contract missed on {address}")
        clock = fact.get("clock", {})
        if (
            clock.get("timezone") not in {"UTC", "Etc/UTC"}
            or clock.get("ntp_synchronized") is not contract["ntp_synchronized"]
        ):
            fail("E_CLOCK", f"clock contract missed on {address}")

    service_contract = requirements["required_active_services"]
    for address in expected:
        services = hosts[address].get("services", {})
        for service in service_contract["all_hosts"] + service_contract[
            "postgresql_hosts"
        ]:
            if services.get(service) != "active":
                fail("E_SERVICE_STATE", f"{service} is not active on {address}")
    control = requirements["target"]["id"] and baseline["target"]["control_node"]
    for service in service_contract["control_host"]:
        if hosts[control].get("services", {}).get(service) != "active":
            fail("E_SERVICE_STATE", f"{service} is not active on control host")


def host_to_cluster(requirements: dict[str, Any]) -> dict[str, str]:
    return {
        member["address"]: unit["id"]
        for unit in requirements["service_units"]
        for member in unit["members"]
    }


def expected_recovery(requirements: dict[str, Any]) -> dict[str, bool]:
    return {
        member["address"]: member["declared_role"] != "primary"
        for unit in requirements["service_units"]
        for member in unit["members"]
    }


def validate_postgresql(
    requirements: dict[str, Any],
    postgres: dict[str, dict[str, Any]],
) -> None:
    initialization = requirements["postgresql_initialization_contract"]
    cluster_for_host = host_to_cluster(requirements)
    recovery_for_host = expected_recovery(requirements)
    system_ids: dict[str, set[str]] = {}
    for address in expected_hosts(requirements):
        fact = postgres[address]
        if (
            fact.get("schema") != "pg36-ch19-postgresql-facts-v1"
            or fact.get("target_ip") != address
            or fact.get("cluster_name") != cluster_for_host[address]
        ):
            fail("E_PG_IDENTITY", f"PostgreSQL identity drifted on {address}")
        if fact.get("in_recovery") is not recovery_for_host[address]:
            fail("E_TOPOLOGY", f"SQL recovery role drifted on {address}")
        if int(fact.get("server_version_num", 0)) // 10000 != initialization["major"]:
            fail("E_PG_INIT", f"PostgreSQL major drifted on {address}")
        settings = fact.get("settings", {})
        if (
            settings.get("data_checksums") != initialization["data_checksums"]
            or settings.get("block_size_bytes") != initialization["block_size_bytes"]
            or settings.get("wal_segment_size_bytes")
            != initialization["wal_segment_size_bytes"]
            or settings.get("timezone") != initialization["timezone"]
            or settings.get("password_encryption")
            != initialization["password_encryption"]
            or settings.get("ssl") != initialization["ssl"]
        ):
            fail("E_PG_INIT", f"PostgreSQL initialization contract drifted on {address}")
        database = fact.get("database_identity", {})
        locale_values = {
            database.get("datcollate"),
            database.get("datctype"),
            database.get("datlocale"),
        }
        if (
            database.get("encoding") != initialization["encoding"]
            or database.get("locale_provider") != initialization["locale_provider"]
            or initialization["locale"] not in locale_values
        ):
            fail("E_PG_INIT", f"database locale/encoding drifted on {address}")
        system_id = str(fact.get("system_identifier", ""))
        if not system_id.isdigit():
            fail("E_PG_IDENTITY", f"system identifier missing on {address}")
        system_ids.setdefault(cluster_for_host[address], set()).add(system_id)
    if any(len(values) != 1 for values in system_ids.values()):
        fail("E_TOPOLOGY", "members of one cluster have different system identifiers")
    if len({next(iter(values)) for values in system_ids.values()}) != len(system_ids):
        fail("E_TOPOLOGY", "separate clusters share one PostgreSQL system identifier")


def validate_patroni(
    requirements: dict[str, Any],
    patroni: dict[str, dict[str, Any]],
    postgres: dict[str, dict[str, Any]],
) -> None:
    expected_by_cluster = {
        unit["id"]: {member["address"] for member in unit["members"]}
        for unit in requirements["service_units"]
    }
    for cluster, expected_members in expected_by_cluster.items():
        fact = patroni.get(cluster, {})
        if (
            fact.get("schema") != "pg36-ch19-patroni-facts-v1"
            or fact.get("cluster") != cluster
        ):
            fail("E_TOPOLOGY", f"Patroni identity drifted for {cluster}")
        rows = fact.get("members")
        if not isinstance(rows, list):
            fail("E_TOPOLOGY", f"Patroni members missing for {cluster}")
        hosts = {str(row.get("host")) for row in rows}
        if hosts != expected_members:
            fail("E_TOPOLOGY", f"Patroni host set drifted for {cluster}")
        primaries = [
            row
            for row in rows
            if normalize_role(row.get("role")) == "primary"
        ]
        if len(primaries) != 1:
            fail("E_TOPOLOGY", f"Patroni {cluster} does not have exactly one leader")
        healthy_states = {"running", "streaming"}
        if any(
            str(row.get("state", "")).lower() not in healthy_states
            for row in rows
        ):
            fail("E_TOPOLOGY", f"Patroni {cluster} has a non-running member")
        for row in rows:
            address = str(row["host"])
            patroni_recovery = normalize_role(row.get("role")) != "primary"
            if postgres[address].get("in_recovery") is not patroni_recovery:
                fail("E_TOPOLOGY", f"Patroni and SQL disagree on {address}")


def validate_endpoints(
    requirements: dict[str, Any],
    endpoints: dict[str, Any],
) -> None:
    if endpoints.get("schema") != "pg36-ch19-endpoint-probes-v1":
        fail("E_ENDPOINT", "endpoint evidence identity drifted")
    rows = endpoints.get("hosts", {})
    required_ports = {"5432", "5433", "5434", "5436", "5438", "8008"}
    for host in expected_hosts(requirements):
        fact = rows.get(host, {})
        tcp = fact.get("tcp", {})
        if any(tcp.get(port) is not True for port in required_ports):
            fail("E_ENDPOINT", f"required sandbox endpoint is unreachable on {host}")
        patroni = fact.get("patroni", {})
        if (
            patroni.get("reachable") is not True
            or str(patroni.get("state", "")).lower() != "running"
        ):
            fail("E_ENDPOINT", f"Patroni REST identity failed on {host}")


def validate_exceptions(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
    hosts: dict[str, dict[str, Any]],
) -> list[str]:
    expected = [
        row["id"]
        for row in requirements.get("accepted_sandbox_exceptions", [])
    ]
    required = {
        "EX19-SHARED-HYPERVISOR",
        "EX19-SINGLE-ETCD",
        "EX19-SINGLE-BACKUP-TARGET",
        "EX19-VIRTUAL-STORAGE",
        "EX19-INVENTORY-SECRETS",
        "EX19-LAB-RESOURCE-FLOOR",
    }
    if (
        baseline.get("required_exception_ids") != expected
        or len(expected) != len(set(expected))
        or set(expected) != required
    ):
        fail("E_EXCEPTION", "required sandbox exception set drifted")
    contract = requirements["host_contract"]
    below_recommendation = [
        address
        for address, fact in hosts.items()
        if fact.get("cpu", {}).get("logical_count", 0)
        < contract["recommended_minimum_cpu_count"]
        or fact.get("memory", {}).get("total_bytes", 0)
        < contract["recommended_minimum_memory_bytes"]
    ]
    if not below_recommendation:
        fail(
            "E_EXCEPTION",
            "resource-floor exception is recorded but no host is below recommendation",
        )
    return expected


def validate_manifest(
    requirements: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    if (
        manifest.get("schema") != "pg36-ch19-capture-manifest-v1"
        or manifest.get("target") != requirements["target"]["id"]
        or manifest.get("mode") != "read-only-ssh-sql-rest-tcp"
        or manifest.get("host_count") != 4
        or manifest.get("postgresql_member_count") != 4
        or manifest.get("patroni_cluster_count") != 2
        or manifest.get("production_approval") is not False
    ):
        fail("E_MANIFEST", "capture manifest identity or boundary drifted")


def validate_bundle(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    validate_document_identity(requirements, baseline)
    validate_production_boundary(requirements, baseline)
    validate_inventory(requirements, evidence["inventory"])
    validate_hosts(requirements, baseline, evidence["hosts"])
    validate_postgresql(requirements, evidence["postgres"])
    validate_patroni(requirements, evidence["patroni"], evidence["postgres"])
    validate_endpoints(requirements, evidence["endpoints"])
    exceptions = validate_exceptions(requirements, baseline, evidence["hosts"])
    validate_manifest(requirements, evidence["manifest"])

    clusters = {
        cluster: next(
            iter(
                {
                    evidence["postgres"][host]["system_identifier"]
                    for host, name in host_to_cluster(requirements).items()
                    if name == cluster
                }
            )
        )
        for cluster in ("pg-meta", "pg-test")
    }
    return {
        "schema": "pg36-ch19-validation-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "decision": {
            "sandbox_l2": "accepted-with-exceptions",
            "production_ch19_gate": "pending",
            "next_gate": "ch20-ha",
        },
        "counts": {
            "hosts": len(evidence["hosts"]),
            "postgresql_members": len(evidence["postgres"]),
            "postgresql_clusters": len(evidence["patroni"]),
            "service_units": len(requirements["service_units"]),
            "accepted_exceptions": len(exceptions),
        },
        "facts": {
            "pigsty_version": evidence["inventory"]["global"]["version"],
            "postgresql_major": requirements["target"]["postgresql_major"],
            "host_os": requirements["host_contract"]["os_version_prefix"],
            "host_architecture": requirements["host_contract"]["architecture"],
            "system_identifiers": clusters,
        },
        "accepted_exception_ids": exceptions,
        "canonical_sha256": {
            "requirements": canonical_sha256(requirements),
            "baseline": canonical_sha256(baseline),
            "inventory_projection": canonical_sha256(evidence["inventory"]),
        },
        "policies": [
            "sandbox-never-claims-production-slo",
            "inventory-evidence-is-secret-free-and-source-mode-0600",
            "addresses-map-to-four-distinct-uniform-linux-machines",
            "clock-resource-and-thp-floor-pass",
            "postgresql-initialization-contract-is-uniform",
            "inventory-patroni-and-sql-topology-agree",
            "service-and-patroni-endpoints-are-reachable",
            "shared-failure-domains-remain-explicit-exceptions",
        ],
    }


def get_path(document: Any, path: list[Any]) -> Any:
    cursor = document
    for segment in path:
        cursor = cursor[segment]
    return cursor


def set_path(document: Any, path: list[Any], value: Any) -> None:
    cursor = document
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value


def apply_patch(documents: dict[str, Any], patch: dict[str, Any]) -> None:
    target = patch.get("target")
    if target not in documents:
        fail("E_NEGATIVE_CASE", f"unknown patch target: {target}")
    path = patch.get("path")
    if not isinstance(path, list) or not path:
        fail("E_NEGATIVE_CASE", "patch path must be a non-empty list")
    operation = patch.get("op")
    if operation == "replace":
        set_path(documents[target], path, patch.get("value"))
    elif operation == "copy":
        source = patch.get("from")
        if not isinstance(source, list) or not source:
            fail("E_NEGATIVE_CASE", "copy patch needs from path")
        set_path(
            documents[target],
            path,
            copy.deepcopy(get_path(documents[target], source)),
        )
    else:
        fail("E_NEGATIVE_CASE", f"unsupported patch operation: {operation}")


def run_negative_suite(
    requirements: dict[str, Any],
    baseline: dict[str, Any],
    evidence: dict[str, Any],
    cases_doc: dict[str, Any],
) -> dict[str, Any]:
    if cases_doc.get("schema") != "pg36-ch19-negative-cases-v1":
        fail("E_SCHEMA", "unexpected negative case schema")
    rows = cases_doc.get("cases")
    if not isinstance(rows, list) or not rows:
        fail("E_NEGATIVE_CASE", "negative suite needs cases")
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        fail("E_NEGATIVE_CASE", "negative case IDs are not unique")
    results: list[dict[str, str]] = []
    for case in rows:
        documents: dict[str, Any] = {
            "requirements": copy.deepcopy(requirements),
            "baseline": copy.deepcopy(baseline),
            **copy.deepcopy(evidence),
        }
        patches = case.get("patches")
        if not isinstance(patches, list) or not patches:
            fail("E_NEGATIVE_CASE", f"case {case.get('id')} needs patches")
        for patch in patches:
            apply_patch(documents, patch)
        actual = "NO_ERROR"
        try:
            validate_bundle(
                documents["requirements"],
                documents["baseline"],
                {
                    key: documents[key]
                    for key in (
                        "inventory",
                        "hosts",
                        "postgres",
                        "patroni",
                        "endpoints",
                        "manifest",
                    )
                },
            )
        except PolicyError as error:
            actual = error.code
        expected = case.get("expected_code")
        if actual != expected:
            fail(
                "E_NEGATIVE_EXPECTATION",
                f"case {case.get('id')} expected {expected}, got {actual}",
            )
        results.append(
            {
                "id": str(case["id"]),
                "expected_code": str(expected),
                "actual_code": actual,
            }
        )
    return {
        "schema": "pg36-ch19-negative-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "case_count": len(results),
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        baseline = read_json(args.baseline)
        evidence = load_evidence(args.evidence, requirements)
        if args.negative_cases:
            report = run_negative_suite(
                requirements,
                baseline,
                evidence,
                read_json(args.negative_cases),
            )
        else:
            report = validate_bundle(requirements, baseline, evidence)
    except PolicyError as error:
        sys.stderr.write(
            json.dumps(
                {
                    "status": "error",
                    "code": error.code,
                    "message": error.message,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 1
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
