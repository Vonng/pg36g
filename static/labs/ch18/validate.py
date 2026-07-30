#!/usr/bin/env python3
"""Cross-document policy validator for the chapter 18 platform blueprint.

Only the Python standard library is used.  The validator deliberately checks
relationships rather than accepting four individually well-formed JSON files:
a reference implementation is useful only when its catalog, data contracts,
extension lifecycle, and lower-volume evidence gates agree.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_CONTRACT_FIELDS = {
    "id",
    "kind",
    "status",
    "owner",
    "authority",
    "source",
    "sink",
    "freshness",
    "delivery",
    "ordering",
    "idempotency",
    "rebuild",
    "failure_mode",
    "reconciliation",
    "deletion",
    "security",
    "exit",
}

REQUIRED_CAPABILITY_FIELDS = {
    "id",
    "owner",
    "placement",
    "system_of_record",
    "state",
    "consistency",
    "freshness",
    "evidence",
    "external_contract_ids",
    "externalization_trigger",
}

EXPECTED_GATE_IDS = [
    "ch19-deployment-baseline",
    "ch20-ha",
    "ch21-backup-restore",
    "ch22-access-routing",
    "ch23-security",
    "ch24-governance",
    "ch25-observability",
    "ch26-capacity",
    "ch27-tuning",
    "ch28-vacuum",
    "ch29-migration",
    "ch30-upgrade",
    "ch31-incident",
    "ch32-pitr",
    "ch33-failover-rebuild",
    "ch34-overload",
    "ch35-forensics",
    "ch36-postmortem",
]


class PolicyError(Exception):
    """A stable, machine-testable policy failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code: str, message: str) -> None:
    raise PolicyError(code, message)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        fail("E_DOCUMENT_SHAPE", f"{path.name} must contain a JSON object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def index_unique(rows: list[dict[str, Any]], key: str, code: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            fail(code, f"every row needs a non-empty {key}")
        if value in result:
            fail(code, f"duplicate {key}: {value}")
        result[value] = row
    return result


def require_text(row: dict[str, Any], field: str, code: str, context: str) -> None:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        fail(code, f"{context} needs non-empty {field}")


def validate_documents(
    blueprint: dict[str, Any],
    catalog: dict[str, Any],
    contracts_doc: dict[str, Any],
    gates_doc: dict[str, Any],
) -> dict[str, Any]:
    if blueprint.get("schema") != "pg36-ch18-production-blueprint-v1":
        fail("E_SCHEMA", "unexpected blueprint schema")
    if catalog.get("schema") != "pg36-service-catalog-v1":
        fail("E_SCHEMA", "unexpected service catalog schema")
    if contracts_doc.get("schema") != "pg36-external-data-contracts-v1":
        fail("E_SCHEMA", "unexpected external contract schema")
    if gates_doc.get("schema") != "pg36-lower-volume-gates-v1":
        fail("E_SCHEMA", "unexpected lower-volume gate schema")

    releases = {
        blueprint.get("release"),
        catalog.get("release"),
        contracts_doc.get("release"),
        gates_doc.get("release"),
    }
    if releases != {"1.6-proposal"}:
        fail("E_RELEASE", f"documents do not share one proposal release: {sorted(repr(v) for v in releases)}")

    target = blueprint.get("target")
    if not isinstance(target, dict):
        fail("E_TARGET", "blueprint target must be an object")
    l1_status = target.get("pigsty_l1_validation")
    l1_evidence = target.get("pigsty_l1_evidence")
    if l1_status != "not-run":
        if not isinstance(l1_evidence, list) or not l1_evidence:
            fail("E_L1_EVIDENCE", "Pigsty L1 may not be claimed without an evidence bundle")
    if not isinstance(l1_evidence, list):
        fail("E_L1_EVIDENCE", "pigsty_l1_evidence must be a list")

    offerings = catalog.get("offerings")
    bundles = catalog.get("extension_bundles")
    if not isinstance(offerings, list) or not offerings:
        fail("E_CATALOG", "service catalog needs offerings")
    if not isinstance(bundles, list) or not bundles:
        fail("E_CATALOG", "service catalog needs extension bundles")
    offering_index = index_unique(offerings, "id", "E_CATALOG_ID")
    bundle_index = index_unique(bundles, "id", "E_EXTENSION_ID")

    for offering in offerings:
        for field in (
            "status",
            "environment",
            "service_owner",
            "topology",
            "isolation",
            "backup_class",
        ):
            require_text(offering, field, "E_CATALOG_FIELD", f"offering {offering['id']}")
        if offering.get("environment", "").startswith("production"):
            objectives = offering.get("service_objectives")
            if not isinstance(objectives, dict) or not objectives:
                fail(
                    "E_SERVICE_OBJECTIVE",
                    f"production-oriented offering {offering['id']} needs proposed objectives",
                )
        bundle_ids = offering.get("allowed_extension_bundles")
        if not isinstance(bundle_ids, list) or not bundle_ids:
            fail("E_CATALOG_FIELD", f"offering {offering['id']} needs allowed_extension_bundles")
        unknown = sorted(set(bundle_ids) - set(bundle_index))
        if unknown:
            fail("E_EXTENSION_REF", f"offering {offering['id']} references unknown bundles: {unknown}")

    service_refs = blueprint.get("service_catalog_ids")
    if not isinstance(service_refs, list) or not service_refs:
        fail("E_SERVICE_REF", "blueprint needs service catalog references")
    unknown_services = sorted(set(service_refs) - set(offering_index))
    if unknown_services:
        fail("E_SERVICE_REF", f"blueprint references unknown offerings: {unknown_services}")

    contract_rows = contracts_doc.get("contracts")
    if not isinstance(contract_rows, list) or not contract_rows:
        fail("E_CONTRACT", "external data contract document needs contracts")
    contract_index = index_unique(contract_rows, "id", "E_CONTRACT_ID")
    for contract in contract_rows:
        missing = sorted(REQUIRED_CONTRACT_FIELDS - set(contract))
        if missing:
            fail("E_CONTRACT_FIELD", f"contract {contract['id']} misses fields: {missing}")
        for field in REQUIRED_CONTRACT_FIELDS - {"authority"}:
            require_text(contract, field, "E_CONTRACT_FIELD", f"contract {contract['id']}")
        authority = contract.get("authority")
        if not isinstance(authority, dict) or not authority:
            fail("E_CONTRACT_FIELD", f"contract {contract['id']} needs domain authority")
        if contract.get("kind") == "cache":
            for domain, owner in authority.items():
                if "business_state" in domain and owner != "postgresql":
                    fail(
                        "E_CACHE_AUTHORITY",
                        f"cache contract {contract['id']} makes {owner!r} authoritative for {domain}",
                    )

    blueprint_contract_ids = blueprint.get("external_contract_ids")
    if not isinstance(blueprint_contract_ids, list):
        fail("E_CONTRACT_REF", "blueprint external_contract_ids must be a list")
    if set(blueprint_contract_ids) != set(contract_index):
        fail("E_CONTRACT_REF", "blueprint must reference every and only declared external contract")

    gates = gates_doc.get("gates")
    if not isinstance(gates, list):
        fail("E_GATE_SET", "lower-volume gates must be a list")
    gate_index = index_unique(gates, "gate_id", "E_GATE_ID")
    gate_ids = [row.get("gate_id") for row in gates]
    chapters = [row.get("chapter") for row in gates]
    if gate_ids != EXPECTED_GATE_IDS or chapters != list(range(19, 37)):
        fail("E_GATE_SET", "lower-volume gates must map chapters 19 through 36 in order")
    for gate in gates:
        require_text(gate, "owner", "E_GATE_FIELD", f"gate {gate['gate_id']}")
        if gate.get("status") != "pending":
            fail("E_GATE_STATUS", f"gate {gate['gate_id']} must remain pending in this proposal")
        for field in ("questions", "required_evidence"):
            values = gate.get(field)
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                fail("E_GATE_FIELD", f"gate {gate['gate_id']} needs non-empty {field}")

    if blueprint.get("lower_volume_gate_ids") != EXPECTED_GATE_IDS:
        fail("E_GATE_REF", "blueprint must reference the exact lower-volume gate sequence")

    blueprint_bundles = blueprint.get("extension_bundles")
    if not isinstance(blueprint_bundles, list) or not blueprint_bundles:
        fail("E_EXTENSION", "blueprint needs extension bundle decisions")
    blueprint_bundle_index = index_unique(blueprint_bundles, "id", "E_EXTENSION_ID")
    if set(blueprint_bundle_index) != set(bundle_index):
        fail("E_EXTENSION_REF", "blueprint and catalog extension bundle sets differ")
    for bundle_id, decision in blueprint_bundle_index.items():
        state = decision.get("production_state")
        gate_ids_for_bundle = decision.get("gate_ids")
        if not isinstance(gate_ids_for_bundle, list):
            fail("E_EXTENSION_GATE", f"bundle {bundle_id} gate_ids must be a list")
        unknown = sorted(set(gate_ids_for_bundle) - set(gate_index))
        if unknown:
            fail("E_EXTENSION_GATE", f"bundle {bundle_id} references unknown gates: {unknown}")
        if state in {"accepted-with-l1-gates", "pilot-only", "conditional"} and not gate_ids_for_bundle:
            fail("E_EXTENSION_GATE", f"bundle {bundle_id} needs explicit production gates")
        if bundle_id == "federation-lab":
            auth = decision.get("lab_authentication")
            if (
                state != "lab-only"
                or not isinstance(auth, dict)
                or auth.get("production_permitted") is not False
            ):
                fail("E_FDW_LAB_ONLY", "chapter 17 loopback FDW authentication is lab-only")

    capabilities = blueprint.get("capability_decisions")
    if not isinstance(capabilities, list) or not capabilities:
        fail("E_CAPABILITY", "blueprint needs capability decisions")
    capability_index = index_unique(capabilities, "id", "E_CAPABILITY_ID")
    for capability in capabilities:
        missing = sorted(REQUIRED_CAPABILITY_FIELDS - set(capability))
        if missing:
            fail("E_CAPABILITY_FIELD", f"capability {capability['id']} misses fields: {missing}")
        for field in ("owner", "placement", "system_of_record", "state", "consistency", "freshness"):
            require_text(capability, field, "E_CAPABILITY_FIELD", f"capability {capability['id']}")
        evidence = capability.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            fail("E_CAPABILITY_FIELD", f"capability {capability['id']} needs evidence")
        contract_refs = capability.get("external_contract_ids")
        if not isinstance(contract_refs, list):
            fail("E_CONTRACT_REF", f"capability {capability['id']} contract refs must be a list")
        unknown = sorted(set(contract_refs) - set(contract_index))
        if unknown:
            fail("E_CONTRACT_REF", f"capability {capability['id']} references unknown contracts: {unknown}")
        placement = capability.get("placement", "")
        trigger = capability.get("externalization_trigger")
        if ("external" in placement or capability.get("state") in {"pilot", "conditional"}) and (
            not isinstance(trigger, str) or not trigger.strip()
        ):
            fail("E_CAPABILITY_TRIGGER", f"capability {capability['id']} needs an exit or adoption trigger")

    exit_paths = blueprint.get("exit_paths")
    if not isinstance(exit_paths, list) or not exit_paths or not all(
        isinstance(path, str) and path.strip() for path in exit_paths
    ):
        fail("E_EXIT_PATH", "the blueprint needs non-empty exit paths")

    return {
        "schema": "pg36-ch18-validation-report-v1",
        "release": blueprint["release"],
        "status": "ok",
        "counts": {
            "offerings": len(offering_index),
            "extension_bundles": len(bundle_index),
            "contracts": len(contract_index),
            "capabilities": len(capability_index),
            "lower_volume_gates": len(gate_index),
            "exit_paths": len(exit_paths),
        },
        "canonical_sha256": {
            "blueprint": canonical_sha256(blueprint),
            "catalog": canonical_sha256(catalog),
            "contracts": canonical_sha256(contracts_doc),
            "gates": canonical_sha256(gates_doc),
        },
        "policies": [
            "proposal-is-not-production-approval",
            "pigsty-l1-needs-evidence",
            "service-objectives-are-explicit-proposals",
            "extensions-have-lifecycle-and-gates",
            "lab-fdw-authentication-never-enters-production",
            "derived-copies-name-authority-and-exit",
            "cache-never-owns-business-state",
            "all-lower-volume-gates-remain-pending",
        ],
    }


def apply_patch(document: dict[str, Any], patch: dict[str, Any]) -> None:
    path = patch.get("path")
    if not isinstance(path, list) or not path:
        fail("E_NEGATIVE_CASE", "patch path must be a non-empty list")
    cursor: Any = document
    for segment in path[:-1]:
        cursor = cursor[segment]
    leaf = path[-1]
    operation = patch.get("op")
    if operation == "replace":
        cursor[leaf] = patch.get("value")
    elif operation == "remove":
        del cursor[leaf]
    else:
        fail("E_NEGATIVE_CASE", f"unsupported patch operation: {operation!r}")


def run_negative_suite(
    originals: dict[str, dict[str, Any]], cases_doc: dict[str, Any]
) -> dict[str, Any]:
    if cases_doc.get("schema") != "pg36-ch18-negative-cases-v1":
        fail("E_SCHEMA", "unexpected negative case schema")
    cases = cases_doc.get("cases")
    if not isinstance(cases, list) or not cases:
        fail("E_NEGATIVE_CASE", "negative suite needs cases")
    index_unique(cases, "id", "E_NEGATIVE_CASE")
    results: list[dict[str, str]] = []
    for case in cases:
        expected = case.get("expected_code")
        if not isinstance(expected, str) or not expected:
            fail("E_NEGATIVE_CASE", f"case {case['id']} needs expected_code")
        documents = copy.deepcopy(originals)
        patches = case.get("patches")
        if not isinstance(patches, list) or not patches:
            fail("E_NEGATIVE_CASE", f"case {case['id']} needs patches")
        for patch in patches:
            target = patch.get("target")
            if target not in documents:
                fail("E_NEGATIVE_CASE", f"case {case['id']} has unknown target {target!r}")
            apply_patch(documents[target], patch)
        actual = "NO_ERROR"
        try:
            validate_documents(
                documents["blueprint"],
                documents["catalog"],
                documents["contracts"],
                documents["gates"],
            )
        except PolicyError as error:
            actual = error.code
        if actual != expected:
            fail(
                "E_NEGATIVE_EXPECTATION",
                f"case {case['id']} expected {expected}, got {actual}",
            )
        results.append({"id": case["id"], "expected_code": expected, "actual_code": actual})
    return {
        "schema": "pg36-ch18-negative-report-v1",
        "release": cases_doc.get("release"),
        "status": "ok",
        "case_count": len(results),
        "cases": results,
    }


def write_report(report: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output is None:
        sys.stdout.write(payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    originals = {
        "blueprint": load_json(args.blueprint),
        "catalog": load_json(args.catalog),
        "contracts": load_json(args.contracts),
        "gates": load_json(args.gates),
    }
    try:
        if args.negative_cases:
            report = run_negative_suite(originals, load_json(args.negative_cases))
        else:
            report = validate_documents(
                originals["blueprint"],
                originals["catalog"],
                originals["contracts"],
                originals["gates"],
            )
    except PolicyError as error:
        sys.stderr.write(
            json.dumps(
                {"status": "error", "code": error.code, "message": error.message},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 1
    write_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
