#!/usr/bin/env python3
"""Review ch14 evidence by package, catalog, behavior, and exit contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "pg36 ch14 extension lifecycle lab; safe to rebuild"


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
    document = load_json(path)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    lines = [
        line
        for line in read_text(path).splitlines()
        if line
        and not line.startswith("[context] ")
        and line != "Pager usage is off."
    ]
    try:
        return list(csv.DictReader(lines))
    except csv.Error as exc:
        raise ReviewError(f"cannot parse CSV {path}: {exc}") from exc


def key_value_csv(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    require(
        all(set(row) == {"key", "value"} for row in rows),
        f"{path.name} is not a key/value document",
    )
    result = {row["key"]: row["value"] for row in rows}
    require(
        len(result) == len(rows),
        f"{path.name} contains duplicate keys",
    )
    return result


def review_manifest(
    evidence: Path,
    baseline_path: Path,
) -> str:
    manifest = read_text(evidence / "manifest.txt")
    checksum = canonical_checksum(baseline_path)
    require(
        "database=pg36_shop" in manifest
        and "in_recovery=false" in manifest
        and "model_version=ch04-v1" in manifest
        and "application_role=pg36_app" in manifest
        and "validation_path=direct-postgresql" in manifest
        and "pigsty_reference=4.4" in manifest
        and "pigsty_l1=not-run" in manifest
        and f"release_candidate_checksum={checksum}" in manifest,
        "manifest target or release identity drifted",
    )
    version = re.search(r"server_version=(\d+)\.", manifest)
    require(
        version is not None and 14 <= int(version.group(1)) <= 18,
        "manifest server version is outside the chapter contract",
    )
    return checksum


def review_package_manifest(evidence: Path) -> None:
    package_manifest = read_text(evidence / "package-manifest.txt")
    require(
        "validation_path=direct-postgresql" in package_manifest
        and "pigsty_l1=not-run" in package_manifest
        and "pg_config_version=PostgreSQL 18.4" in package_manifest
        and "server_major=18" in package_manifest,
        "package manifest target drifted",
    )
    for required_name in (
        "pg_trgm.control",
        "pg_trgm--1.3.sql",
        "pg_trgm--1.3--1.4.sql",
        "pg_trgm--1.4--1.5.sql",
        "pg_trgm--1.5--1.6.sql",
        "vector.control",
        "vector--0.8.4.sql",
        "pg_trgm.",
        "vector.",
    ):
        require(
            required_name in package_manifest,
            f"package manifest lacks {required_name}",
        )
    hashes = re.findall(
        r"(?m)^[0-9a-f]{64}\s+\*?.+$",
        package_manifest,
    )
    require(
        len(hashes) >= 9,
        "package manifest does not hash all reviewed support files",
    )


def review_failures(evidence: Path) -> None:
    for name, phrase in (
        ("owner-create-vector", "Must be superuser"),
        ("app-alter-extension", "must be owner"),
    ):
        require(
            read_text(evidence / f"{name}.exit").strip() == "exit=3",
            f"{name} exit contract drifted",
        )
        stderr = read_text(evidence / f"{name}.stderr")
        require(
            "42501" in stderr and phrase in stderr,
            f"{name} SQLSTATE or reason drifted",
        )


def review_candidates(evidence: Path) -> None:
    before = {
        row["extension_name"]: row
        for row in read_csv(
            evidence / "available-candidates-before.csv"
        )
    }
    after = {
        row["extension_name"]: row
        for row in read_csv(
            evidence / "available-candidates-after.csv"
        )
    }
    require(
        set(before) == {"pg_trgm", "vector", "citus"}
        and set(after) == set(before),
        "candidate inventory drifted",
    )
    expected = {
        "pg_trgm": (
            "pgsql-main",
            "accept",
            "t",
            "1.6",
            "1.3",
            "1.6",
        ),
        "vector": (
            "pgvector",
            "pilot",
            "t",
            "0.8.4",
            "0.8.4",
            "0.8.4",
        ),
        "citus": (
            "citus",
            "reject",
            "f",
            "",
            "",
            "",
        ),
    }
    for extension_name, attributes in expected.items():
        before_row = before[extension_name]
        after_row = after[extension_name]
        actual = (
            before_row["package_alias"],
            before_row["decision"],
            before_row["locally_available"],
            before_row["default_version"],
            before_row["installed_version"],
            after_row["installed_version"],
        )
        require(
            actual == attributes,
            f"candidate decision or availability drifted: {extension_name}",
        )


def review_inventory(evidence: Path) -> None:
    before = {
        row["extension_name"]: row
        for row in read_csv(
            evidence / "extension-inventory-before.csv"
        )
    }
    after = {
        row["extension_name"]: row
        for row in read_csv(
            evidence / "extension-inventory-after.csv"
        )
    }
    require(
        set(before) == {"pg_trgm", "vector"}
        and set(after) == set(before),
        "extension inventory drifted",
    )

    require(
        before["pg_trgm"]["object_version"] == "1.3"
        and after["pg_trgm"]["object_version"] == "1.6"
        and before["pg_trgm"]["owner_name"] == "pg36_owner"
        and after["pg_trgm"]["owner_name"] == "pg36_owner"
        and before["pg_trgm"]["trusted"] == "t"
        and after["pg_trgm"]["trusted"] == "t",
        "pg_trgm lifecycle contract drifted",
    )
    require(
        before["vector"]["object_version"] == "0.8.4"
        and after["vector"]["object_version"] == "0.8.4"
        and before["vector"]["trusted"] == "f"
        and after["vector"]["trusted"] == "f"
        and before["vector"]["owner_name"] != "pg36_owner",
        "vector privilege or version contract drifted",
    )
    for row in (*before.values(), *after.values()):
        require(
            row["schema_name"] == "shop_ch14"
            and row["relocatable"] == "t"
            and row["superuser"] == "t"
            and row["marker"] == MARKER,
            f"extension attributes drifted: {row['extension_name']}",
        )
    require(
        int(before["pg_trgm"]["member_count"]) == 37
        and int(after["pg_trgm"]["member_count"]) == 47
        and int(before["vector"]["member_count"]) == 237
        and int(after["vector"]["member_count"]) == 237,
        "formal PG18.4 extension member count drifted",
    )

    for phase, inventory in (("before", before), ("after", after)):
        rows = read_csv(evidence / f"member-catalog-{phase}.csv")
        totals: dict[str, int] = {}
        for row in rows:
            totals[row["extension_name"]] = (
                totals.get(row["extension_name"], 0)
                + int(row["member_count"])
            )
        require(
            totals
            == {
                name: int(row["member_count"])
                for name, row in inventory.items()
            },
            f"{phase} extension membership decomposition drifted",
        )


def review_versions_and_paths(evidence: Path) -> None:
    before = {
        (row["extension_name"], row["version"]): row
        for row in read_csv(
            evidence / "available-versions-before.csv"
        )
    }
    after = {
        (row["extension_name"], row["version"]): row
        for row in read_csv(
            evidence / "available-versions-after.csv"
        )
    }
    require(
        before[("pg_trgm", "1.3")]["installed"] == "t"
        and before[("pg_trgm", "1.6")]["installed"] == "f"
        and after[("pg_trgm", "1.3")]["installed"] == "f"
        and after[("pg_trgm", "1.6")]["installed"] == "t"
        and before[("vector", "0.8.4")]["installed"] == "t"
        and after[("vector", "0.8.4")]["installed"] == "t",
        "available-version installed flags drifted",
    )
    require(
        before[("pg_trgm", "1.6")]["trusted"] == "t"
        and before[("vector", "0.8.4")]["trusted"] == "f",
        "control-file trusted attributes drifted",
    )
    paths = read_csv(evidence / "update-paths.csv")
    require(
        any(
            row["source"] == "1.3"
            and row["target"] == "1.6"
            and row["path"] == "1.3--1.4--1.5--1.6"
            for row in paths
        ),
        "pg_trgm 1.3 to 1.6 update path is missing",
    )


def review_indexes_and_security(evidence: Path) -> None:
    expected_indexes = {
        "candidate_doc_title_trgm_idx": (
            "gin",
            "shop_ch14.gin_trgm_ops",
        ),
        "candidate_doc_embedding_hnsw_idx": (
            "hnsw",
            "shop_ch14.vector_l2_ops",
        ),
    }
    for phase in ("before", "after"):
        rows = {
            row["index_name"]: row
            for row in read_csv(
                evidence / f"index-catalog-{phase}.csv"
            )
        }
        require(
            set(rows) == set(expected_indexes),
            f"{phase} index inventory drifted",
        )
        for index_name, attributes in expected_indexes.items():
            row = rows[index_name]
            require(
                (
                    row["access_method"],
                    row["operator_class"],
                )
                == attributes
                and row["is_valid"] == "t"
                and row["is_ready"] == "t"
                and row["is_live"] == "t"
                and row["marker"] == MARKER,
                f"{phase} index contract drifted: {index_name}",
            )

        security = key_value_csv(
            evidence / f"security-catalog-{phase}.csv"
        )
        require(
            security
            == {
                "app_doc_delete": "false",
                "app_doc_insert": "false",
                "app_doc_select": "true",
                "app_doc_update": "false",
                "app_review_select": "true",
                "app_schema_usage": "true",
                "pg_trgm_owned_by_owner": "true",
                "vector_owned_by_superuser": "true",
            },
            f"{phase} least-privilege matrix drifted",
        )


def review_behavior(evidence: Path) -> None:
    before = key_value_csv(evidence / "behavior-before.csv")
    after = key_value_csv(evidence / "behavior-after.csv")
    stable = {
        "trigram_scores": "0.620690,0.305556,0.205128",
        "trigram_top_ids": "1,5,2",
        "vector_distances": "0.000000,0.141421,0.282843",
        "vector_top_ids": "1,2,5",
        "vector_version": "0.8.4",
    }
    require(
        before == {**stable, "pg_trgm_version": "1.3"}
        and after == {**stable, "pg_trgm_version": "1.6"},
        "query behavior changed across extension update",
    )

    for phase in ("before", "after"):
        trigram_plan = read_text(
            evidence / f"trigram-plan-{phase}.txt"
        )
        vector_plan = read_text(
            evidence / f"vector-plan-{phase}.txt"
        )
        require(
            "Bitmap Index Scan on candidate_doc_title_trgm_idx"
            in trigram_plan
            and "Index Scan using candidate_doc_embedding_hnsw_idx"
            in vector_plan,
            f"{phase} forced index evidence drifted",
        )

    app_query = read_text(evidence / "app-query.csv")
    for required_value in (
        "PostgreSQL extension guide",
        "Native PostgreSQL indexing",
        "Pigsty extension operations",
        "0.620690",
        "0.141421",
        "0.282843",
    ):
        require(
            required_value in app_query,
            f"application query evidence lacks {required_value}",
        )


def review_dump_and_exit(evidence: Path) -> None:
    database_dump = read_text(evidence / "database-schema.sql")
    selected_dump = read_text(evidence / "selected-schema.sql")

    require(
        "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA shop_ch14;"
        in database_dump
        and "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA shop_ch14;"
        in database_dump
        and "COMMENT ON EXTENSION pg_trgm IS" in database_dump
        and "COMMENT ON EXTENSION vector IS" in database_dump,
        "database schema dump lacks extension declarations",
    )
    require(
        "CREATE FUNCTION shop_ch14." not in database_dump
        and "CREATE TYPE shop_ch14.vector" not in database_dump,
        "database dump incorrectly expands extension members",
    )
    require(
        "CREATE TABLE shop_ch14.candidate_doc" in selected_dump
        and "candidate_doc_embedding_hnsw_idx" in selected_dump
        and "candidate_doc_title_trgm_idx" in selected_dump
        and "CREATE EXTENSION" not in selected_dump,
        "selective schema dump dependency lesson drifted",
    )

    portable_lines = [
        line
        for line in read_text(
            evidence / "portable-export.csv"
        ).splitlines()
        if line and line != "Pager usage is off."
    ]
    portable_rows = list(csv.DictReader(portable_lines))
    require(
        len(portable_rows) == 5
        and set(portable_rows[0])
        == {"doc_id", "title", "embedding_text"}
        and [row["doc_id"] for row in portable_rows]
        == ["1", "2", "3", "4", "5"]
        and all(
            re.fullmatch(r"\[[0-9.,-]+\]", row["embedding_text"])
            for row in portable_rows
        ),
        "portable vector export drifted",
    )


def review_final_state(
    evidence: Path,
    baseline: dict[str, Any],
) -> None:
    final_state = key_value_csv(evidence / "final-state.csv")
    expected_state = baseline["expected_state"]
    require(
        final_state
        == {
            "business_checksum": expected_state[
                "business_checksum"
            ],
            "document_rows": str(expected_state["documents"]),
            "pg_trgm_members": str(
                expected_state["pg_trgm_members_on_18_4"]
            ),
            "pg_trgm_version": "1.6",
            "release": baseline["release"],
            "review_rows": str(expected_state["reviews"]),
            "trigram_top_ids": "1,5,2",
            "vector_members": str(
                expected_state["vector_members_on_18_4"]
            ),
            "vector_top_ids": "1,2,5",
            "vector_version": "0.8.4",
        },
        "final extension-lifecycle state drifted",
    )
    verify = read_text(evidence / "verify.txt")
    for line in (
        "status=ok",
        "boundary=package+control+database-object",
        "decision=pg_trgm:accept/vector:pilot/citus:reject",
        "upgrade=pg_trgm:1.3->1.6",
        "failure=42501-owner+42501-superuser",
        "exit=portable-text-export",
    ):
        require(
            line in verify,
            f"verify output lacks {line}",
        )
    require(
        "status=ok" in read_text(
            evidence / "model-verify-after.txt"
        ),
        "upstream ch04-v1 model verification failed",
    )


def review_source_contract(repo_root: Path) -> None:
    lab_dir = repo_root / "static" / "labs" / "ch14"
    required_sources = {
        "baseline-v1.2-proposal.json",
        "candidate-review.md",
        "extension-adr-template.md",
        "lab-contract.md",
        "pigsty-declaration.example.yml",
        "reset.sql",
        "setup.sql",
        "task.sh",
        "verify.sql",
    }
    require(
        required_sources.issubset(
            {path.name for path in lab_dir.iterdir()}
        ),
        "chapter source contract is incomplete",
    )
    task_source = read_text(lab_dir / "task.sh")
    reset_source = read_text(lab_dir / "reset.sql")
    require(
        "DROP EXTENSION vector;" in reset_source
        and "DROP EXTENSION pg_trgm;" in reset_source
        and "CASCADE" not in reset_source.upper()
        and "run_reset_guards" in task_source,
        "reset source lost its exact no-CASCADE contract",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    evidence = args.evidence_dir.resolve()
    repo_root = args.repo_root.resolve()
    baseline_path = (
        repo_root
        / "static"
        / "labs"
        / "ch14"
        / "baseline-v1.2-proposal.json"
    )
    baseline = load_json(baseline_path)

    try:
        checksum = review_manifest(evidence, baseline_path)
        review_package_manifest(evidence)
        review_failures(evidence)
        review_candidates(evidence)
        review_inventory(evidence)
        review_versions_and_paths(evidence)
        review_indexes_and_security(evidence)
        review_behavior(evidence)
        review_dump_and_exit(evidence)
        review_final_state(evidence, baseline)
        review_source_contract(repo_root)
    except ReviewError as exc:
        print(f"review_error={exc}", file=sys.stderr)
        return 1

    print("status=ok")
    print("decision=pg_trgm:accept/vector:pilot/citus:reject")
    print("boundary=package+control+database-object")
    print("failure=42501-owner+42501-superuser")
    print("upgrade=pg_trgm:1.3->1.6-behavior-stable")
    print("index=gin+hnsw")
    print("dump=create-extension+selective-dependency-warning")
    print("exit=portable-text-export")
    print("pigsty_l1=not-run")
    print(f"release={baseline['release']}")
    print(f"release_candidate_checksum={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
