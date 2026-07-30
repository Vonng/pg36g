#!/usr/bin/env python3
"""Review the chapter 18 read-only platform audit evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


RELATION_CHECKSUM = "f8a7bfae59c6d16cd323abecfefe1014"

EXPECTED_CAPABILITIES = [
    ("relational-core", "accepted", "ch04-v1"),
    ("atomic-database-logic", "accepted-with-scope", "ch13-routine-guard-v1"),
    ("lexical-and-fuzzy-search", "accepted", "pg_trgm:1.6"),
    ("semantic-search", "pilot", "vector:0.8.4"),
    ("spatiotemporal", "conditional", "btree_gist:1.8,postgis:3.6.4"),
    ("analytical-federation", "lab-only", "postgres_fdw:1.2"),
    ("search-quality-fixture", "accepted", "ch15-search-v1"),
    ("spatiotemporal-fixture", "accepted", "ch16-spatiotemporal-v1"),
    ("analytics-fixture", "accepted", "ch17-analytics-v1"),
]

EXPECTED_EXTENSIONS = {
    "btree_gist": ("1.8", "shop_ch16_ext", "pg36_owner", "t"),
    "pg_trgm": ("1.6", "shop_ch14", "pg36_owner", "t"),
    "plpgsql": ("1.0", "pg_catalog", "postgres", "f"),
    "postgis": ("3.6.4", "shop_ch16_ext", "postgres", "f"),
    "postgres_fdw": ("1.2", "shop_ch17_ext", "postgres", "t"),
    "vector": ("0.8.4", "shop_ch14", "postgres", "t"),
}

EXPECTED_SCHEMA_COMMENTS = {
    "shop": "Canonical pg36_shop business relations",
    "shop_private": "Owner-only internal namespace for future implementation objects",
    "shop_ch13": "pg36 ch13 routine guard lab; safe to rebuild",
    "shop_ch14": "pg36 ch14 extension lifecycle lab; safe to rebuild",
    "shop_ch15": "pg36 ch15 search quality lab; safe to rebuild",
    "shop_ch16": "pg36 ch16 spatiotemporal lab; safe to rebuild",
    "shop_ch16_ext": "pg36 ch16 spatiotemporal lab; safe to rebuild",
    "shop_ch17": "pg36 ch17 analytics fdw lab; safe to rebuild",
    "shop_ch17_ext": "pg36 ch17 analytics fdw lab; safe to rebuild",
}

EXPECTED_NEGATIVE_CODES = {
    "claim-l1-without-evidence": "E_L1_EVIDENCE",
    "remove-every-exit-path": "E_EXIT_PATH",
    "make-cache-authoritative": "E_CACHE_AUTHORITY",
    "delete-contract-rebuild": "E_CONTRACT_FIELD",
    "admit-loopback-fdw-to-production": "E_FDW_LAB_ONLY",
    "remove-production-objectives": "E_SERVICE_OBJECTIVE",
    "remove-pilot-gates": "E_EXTENSION_GATE",
}


class ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise ReviewError(f"cannot parse JSON {path}: {exc}") from exc


def canonical_checksum(path: Path) -> str:
    encoded = json.dumps(
        load_json(path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        return list(csv.DictReader(read_text(path).splitlines()))
    except csv.Error as exc:
        raise ReviewError(f"cannot parse CSV {path}: {exc}") from exc


def index_rows(
    rows: list[dict[str, str]], key: str, source: str
) -> dict[str, dict[str, str]]:
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"{source} contains duplicate {key}")
    return result


def review_manifest(evidence: Path, source: Path) -> None:
    manifest = read_text(evidence / "manifest.txt")
    expected_lines = {
        "database=pg36_shop",
        "admin_session_user=postgres",
        "in_recovery=false",
        "validation_path=read-only-postgresql-catalog+cross-document-policy",
        "pigsty_reference=4.4",
        "pigsty_l1=not-run",
        "model_version=ch04-v1",
        "mutation=none",
        "upper_volume_preflight=ch04+ch13+ch14+ch15+ch16+ch17",
    }
    for line in expected_lines:
        require(line in manifest, f"manifest misses {line}")
    version = re.search(r"^server_version=(\d+)\.", manifest, re.MULTILINE)
    require(
        version is not None and int(version.group(1)) == 18,
        "formal fixture was not captured on PostgreSQL 18.x",
    )
    for name in (
        "baseline-v1.6-proposal.json",
        "service-catalog.json",
        "external-data-contracts.json",
        "lower-volume-gates.json",
        "negative-cases.json",
    ):
        checksum = canonical_checksum(source / name)
        require(
            f"{name}_canonical_sha256={checksum}" in manifest,
            f"manifest canonical checksum drifted for {name}",
        )


def review_platform_state(evidence: Path) -> None:
    rows = read_csv(evidence / "platform-state.csv")
    require(
        all(set(row) == {"key", "value"} for row in rows),
        "platform-state.csv is not key/value evidence",
    )
    state = {row["key"]: row["value"] for row in rows}
    require(len(state) == len(rows), "platform state contains duplicate keys")
    require(
        state.get("database") == "pg36_shop"
        and state.get("server_major") == "18"
        and state.get("session_user") == "postgres"
        and state.get("in_recovery") == "false"
        and state.get("model_version") == "ch04-v1"
        and state.get("relation_checksum") == RELATION_CHECKSUM
        and state.get("pigsty_reference") == "4.4"
        and state.get("pigsty_l1") == "not-run"
        and state.get("mutation") == "none",
        "platform identity, fixture, or mutation state drifted",
    )
    require(
        state.get("server_version", "").startswith("18."),
        "server version was not captured",
    )


def review_extensions(evidence: Path) -> None:
    rows = read_csv(evidence / "extension-catalog.csv")
    by_name = index_rows(rows, "extension_name", "extension-catalog.csv")
    require(set(by_name) == set(EXPECTED_EXTENSIONS), "extension set drifted")
    for name, expected in EXPECTED_EXTENSIONS.items():
        row = by_name[name]
        actual = (
            row["extension_version"],
            row["schema_name"],
            row["owner_name"],
            row["relocatable"],
        )
        require(actual == expected, f"extension identity drifted for {name}: {actual}")
        if name != "plpgsql":
            require(
                row["comment"].startswith("pg36 ch"),
                f"teaching extension {name} lost its safety marker",
            )


def review_schemas(evidence: Path) -> None:
    rows = read_csv(evidence / "schema-catalog.csv")
    by_name = index_rows(rows, "schema_name", "schema-catalog.csv")
    require(set(by_name) == set(EXPECTED_SCHEMA_COMMENTS), "schema set drifted")
    for name, comment in EXPECTED_SCHEMA_COMMENTS.items():
        row = by_name[name]
        require(row["owner_name"] == "pg36_owner", f"schema owner drifted for {name}")
        require(row["comment"] == comment, f"schema marker drifted for {name}")
        require(
            int(row["relation_count"]) >= 0 and int(row["routine_count"]) >= 0,
            f"schema counts are invalid for {name}",
        )


def review_roles(evidence: Path) -> None:
    rows = read_csv(evidence / "role-catalog.csv")
    by_name = index_rows(rows, "role_name", "role-catalog.csv")
    require(set(by_name) == {"pg36_app", "pg36_owner", "postgres"}, "role set drifted")
    require(
        by_name["pg36_app"]["can_login"] == "t"
        and by_name["pg36_app"]["is_superuser"] == "f"
        and by_name["pg36_app"]["bypass_rls"] == "f",
        "pg36_app privilege boundary drifted",
    )
    require(
        by_name["pg36_owner"]["can_login"] == "f"
        and by_name["pg36_owner"]["is_superuser"] == "f",
        "pg36_owner privilege boundary drifted",
    )
    require(
        by_name["postgres"]["can_login"] == "t"
        and by_name["postgres"]["is_superuser"] == "t",
        "formal fixture administrator identity drifted",
    )


def review_capabilities(evidence: Path) -> None:
    rows = read_csv(evidence / "capability-snapshot.csv")
    actual = [
        (row["capability_id"], row["lifecycle"], row["evidence"])
        for row in rows
    ]
    require(actual == EXPECTED_CAPABILITIES, "capability evidence or lifecycle drifted")


def review_policy_reports(evidence: Path, source: Path) -> None:
    report = load_json(evidence / "validation-report.json")
    require(
        report.get("schema") == "pg36-ch18-validation-report-v1"
        and report.get("release") == "1.6-proposal"
        and report.get("status") == "ok",
        "normal validation report identity drifted",
    )
    require(
        report.get("counts")
        == {
            "offerings": 4,
            "extension_bundles": 5,
            "contracts": 5,
            "capabilities": 9,
            "lower_volume_gates": 18,
            "exit_paths": 5,
        },
        "platform document counts drifted",
    )
    expected_checksums = {
        "blueprint": canonical_checksum(source / "baseline-v1.6-proposal.json"),
        "catalog": canonical_checksum(source / "service-catalog.json"),
        "contracts": canonical_checksum(source / "external-data-contracts.json"),
        "gates": canonical_checksum(source / "lower-volume-gates.json"),
    }
    require(
        report.get("canonical_sha256") == expected_checksums,
        "policy report document checksums drifted",
    )

    negative = load_json(evidence / "negative-report.json")
    require(
        negative.get("schema") == "pg36-ch18-negative-report-v1"
        and negative.get("status") == "ok"
        and negative.get("case_count") == len(EXPECTED_NEGATIVE_CODES),
        "negative report identity drifted",
    )
    actual_codes = {
        row["id"]: row["actual_code"]
        for row in negative.get("cases", [])
    }
    expected_codes = {
        row["id"]: row["expected_code"]
        for row in negative.get("cases", [])
    }
    require(
        actual_codes == EXPECTED_NEGATIVE_CODES
        and expected_codes == EXPECTED_NEGATIVE_CODES,
        "negative policy suite did not reject the intended counterexamples",
    )


def review_stderr(evidence: Path) -> None:
    for path in sorted(evidence.glob("*.stderr")):
        require(not read_text(path).strip(), f"{path.name} is not empty")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        review_manifest(args.evidence, args.source_dir)
        review_platform_state(args.evidence)
        review_extensions(args.evidence)
        review_schemas(args.evidence)
        review_roles(args.evidence)
        review_capabilities(args.evidence)
        review_policy_reports(args.evidence, args.source_dir)
        review_stderr(args.evidence)
    except ReviewError as error:
        sys.stderr.write(f"review failed: {error}\n")
        return 1
    print("status=ok")
    print("audit=read-only-upper-volume-capability-map")
    print("documents=catalog+contracts+blueprint+18-pending-gates")
    print("counterexamples=7-rejected")
    print("pigsty_l1=not-run")
    print("mutation=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
