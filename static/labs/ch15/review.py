#!/usr/bin/env python3
"""Review chapter 15 evidence without treating tiny-fixture sizes as a benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "pg36 ch15 search quality lab; safe to rebuild"


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


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
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


def sha256(path: Path) -> str:
    return hashlib.sha256(read_bytes(path)).hexdigest()


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
    baseline: Path,
    fixture_manifest: Path,
) -> str:
    manifest = read_text(evidence / "manifest.txt")
    baseline_checksum = canonical_checksum(baseline)
    fixture_checksum = canonical_checksum(fixture_manifest)
    require(
        "database=pg36_shop" in manifest
        and "in_recovery=false" in manifest
        and "model_version=ch04-v1" in manifest
        and "extension_versions=pg_trgm:1.6,vector:0.8.4"
        in manifest
        and "embedding_model=pg36-handcrafted-topic-4d-v1"
        in manifest
        and "validation_path=direct-postgresql" in manifest
        and "pigsty_reference=4.4" in manifest
        and "pigsty_l1=not-run" in manifest
        and f"release_candidate_checksum={baseline_checksum}"
        in manifest
        and f"fixture_manifest_checksum={fixture_checksum}"
        in manifest,
        "manifest target, dependency, or release identity drifted",
    )
    version = re.search(r"server_version=(\d+)\.", manifest)
    require(
        version is not None and 14 <= int(version.group(1)) <= 18,
        "manifest server version is outside the chapter contract",
    )
    return baseline_checksum


def review_fixture_sources(
    evidence: Path,
    source_dir: Path,
    fixture_manifest_path: Path,
) -> None:
    fixture_manifest = load_json(fixture_manifest_path)
    pairs = (
        ("corpus", "frozen-corpus.csv", "corpus.csv"),
        ("queries", "frozen-queries.csv", "queries.csv"),
        ("judgments", "frozen-judgments.csv", "judgments.csv"),
    )
    for key, source_name, evidence_name in pairs:
        source = source_dir / source_name
        exported = evidence / evidence_name
        require(
            read_bytes(source) == read_bytes(exported),
            f"{evidence_name} is not a byte-identical database export",
        )
        require(
            sha256(source) == fixture_manifest[key]["sha256"],
            f"{source_name} hash drifted from fixture manifest",
        )
        rows = read_csv(source)
        require(
            len(rows) == fixture_manifest[key]["rows"],
            f"{source_name} row count drifted",
        )
    loader = source_dir / fixture_manifest["loader"]["path"]
    require(
        sha256(loader) == fixture_manifest["loader"]["sha256"],
        "fixture.sql hash drifted from fixture manifest",
    )
    embedding = fixture_manifest["embedding"]
    require(
        embedding["model_id"] == "pg36-handcrafted-topic-4d-v1"
        and embedding["dimensions"] == 4
        and embedding["distance"] == "L2"
        and embedding["external_model"] is False
        and embedding["external_api"] is False,
        "fixture embedding identity drifted",
    )


def review_catalogs(evidence: Path) -> None:
    documents = read_csv(evidence / "document-catalog.csv")
    require(
        len(documents) == 17
        and {row["product_id"] for row in documents}
        == {str(value) for value in range(1, 18)}
        and [row["product_id"] for row in documents if row["active"] == "f"]
        == ["17"]
        and all(
            row["embedding_model"]
            == "pg36-handcrafted-topic-4d-v1"
            and row["search_document"]
            for row in documents
        ),
        "document catalog or generated vectors drifted",
    )

    indexes = {
        row["index_name"]: row
        for row in read_csv(evidence / "index-catalog.csv")
    }
    require(
        set(indexes)
        == {
            "product_search_fts_idx",
            "product_search_title_trgm_idx",
            "product_search_embedding_hnsw_idx",
            "product_search_filter_idx",
        },
        "search index inventory drifted",
    )
    expected = {
        "product_search_fts_idx": ("gin", "pg_catalog.tsvector_ops"),
        "product_search_title_trgm_idx": (
            "gin",
            "shop_ch14.gin_trgm_ops",
        ),
        "product_search_embedding_hnsw_idx": (
            "hnsw",
            "shop_ch14.vector_l2_ops",
        ),
        "product_search_filter_idx": (
            "btree",
            "pg_catalog.text_ops",
        ),
    }
    for name, (access_method, operator_class) in expected.items():
        row = indexes[name]
        require(
            row["access_method"] == access_method
            and row["operator_class"] == operator_class
            and row["is_valid"] == "t"
            and row["is_ready"] == "t"
            and row["is_live"] == "t"
            and row["marker"] == MARKER
            and int(row["index_bytes"]) > 0,
            f"index contract drifted: {name}",
        )

    sizes = read_csv(evidence / "size-catalog.csv")
    require(
        {row["object_name"] for row in sizes}
        == {
            "filter_btree",
            "fts_gin",
            "product_heap",
            "product_total",
            "trigram_gin",
            "vector_hnsw",
        }
        and all(int(row["bytes"]) > 0 for row in sizes),
        "size evidence is incomplete",
    )

    security = key_value_csv(evidence / "security-catalog.csv")
    require(
        security
        == {
            "app_product_delete": "false",
            "app_product_insert": "false",
            "app_product_select": "true",
            "app_product_update": "false",
            "app_quality_select": "true",
            "app_schema_usage": "true",
        },
        "application privilege boundary drifted",
    )


def review_text_search(evidence: Path) -> None:
    rows = read_csv(evidence / "fts-analysis.csv")
    require(
        len(rows) == 8,
        "full-text analysis query count drifted",
    )
    expected_matches = {
        "q01": "1",
        "q02": "0",
        "q03": "1",
        "q04": "1",
        "q05": "1",
        "q06": "2",
        "q07": "0",
        "q08": "1",
    }
    require(
        {row["query_id"]: row["matched_products"] for row in rows}
        == expected_matches
        and all(int(row["node_count"]) > 0 for row in rows),
        "full-text parsing or match behavior drifted",
    )


def review_quality(evidence: Path) -> None:
    rows = {
        row["strategy"]: row
        for row in read_csv(evidence / "quality-summary.csv")
    }
    expected = {
        "fuzzy": (
            "0.916667",
            "0.916667",
            "1.000000",
            "0.942881",
            "0.842828",
        ),
        "hybrid_rrf": (
            "1.000000",
            "1.000000",
            "1.000000",
            "0.962929",
            "0.759192",
        ),
        "lexical": (
            "0.291667",
            "0.291667",
            "0.750000",
            "0.613043",
            "0.000000",
        ),
        "vector_exact": (
            "1.000000",
            "1.000000",
            "1.000000",
            "0.817314",
            "0.631039",
        ),
    }
    require(set(rows) == set(expected), "quality strategy set drifted")
    for strategy, values in expected.items():
        row = rows[strategy]
        actual = (
            row["mean_precision_at_3"],
            row["mean_recall_at_3"],
            row["mrr_at_3"],
            row["mean_ndcg_at_3"],
            row["min_ndcg_at_3"],
        )
        require(
            row["query_count"] == "8" and actual == values,
            f"quality baseline drifted: {strategy}",
        )

    detail = read_csv(evidence / "quality-detail.csv")
    require(
        len(detail) == 32
        and all(row["relevant_count"] == "3" for row in detail),
        "per-query quality grid is incomplete",
    )
    by_key = {
        (row["strategy"], row["query_id"]): row
        for row in detail
    }
    require(
        by_key[("lexical", "q02")]["result_count"] == "0"
        and by_key[("lexical", "q07")]["result_count"] == "0"
        and by_key[("hybrid_rrf", "q02")]["ndcg_at_3"]
        == "0.759192"
        and by_key[("fuzzy", "q02")]["ndcg_at_3"]
        == "0.842828",
        "pedagogical counterexamples drifted",
    )

    rankings = read_csv(evidence / "ranking-results.csv")
    require(
        len(rankings) == 79
        and all(row["product_id"] != "17" for row in rankings),
        "top-three ranking evidence is incomplete or leaked inactive data",
    )
    hybrid = {
        row["query_id"]: []
        for row in rankings
        if row["strategy"] == "hybrid_rrf"
    }
    for row in rankings:
        if row["strategy"] == "hybrid_rrf":
            hybrid[row["query_id"]].append(row["product_id"])
    require(
        hybrid
        == {
            "q01": ["1", "2", "3"],
            "q02": ["3", "2", "1"],
            "q03": ["2", "1", "3"],
            "q04": ["4", "6", "5"],
            "q05": ["5", "6", "4"],
            "q06": ["7", "8", "9"],
            "q07": ["10", "11", "12"],
            "q08": ["12", "10", "11"],
        },
        "hybrid ranking contract drifted",
    )


def review_ann_and_plans(evidence: Path) -> None:
    ann = read_csv(evidence / "ann-compare.csv")
    require(
        ann
        == [
            {
                "exact_ids": "7,8,9",
                "ann_ids": "7,8,9",
                "recall_at_3": "1.000000",
            }
        ],
        "exact-to-HNSW recall probe drifted",
    )
    plan_expectations = {
        "fts-plan.txt": (
            "Bitmap Index Scan on product_search_fts_idx",
        ),
        "trigram-plan.txt": (
            "Bitmap Index Scan on product_search_title_trgm_idx",
        ),
        "vector-exact-plan.txt": ("Seq Scan on product_search", "Sort Key:"),
        "vector-hnsw-plan.txt": (
            "Index Scan using product_search_embedding_hnsw_idx",
        ),
        "vector-filtered-plan.txt": (
            "Index Scan using product_search_embedding_hnsw_idx",
            "Filter:",
        ),
    }
    for name, fragments in plan_expectations.items():
        plan = read_text(evidence / name)
        require(
            all(fragment in plan for fragment in fragments),
            f"execution path evidence drifted: {name}",
        )


def review_security_failure(evidence: Path) -> None:
    require(
        read_text(evidence / "app-write.exit").strip() == "exit=3",
        "application write exit contract drifted",
    )
    stderr = read_text(evidence / "app-write.stderr")
    require(
        "42501" in stderr
        and "permission denied for table product_search" in stderr,
        "application write SQLSTATE or reason drifted",
    )
    app_query = read_text(evidence / "app-query.csv")
    require(
        "wireles hedphones" not in app_query
        and "Wireless Noise-Canceling Headphones" in app_query
        and "Vector Search Engineering Guide" in app_query
        and "hybrid_rrf" in app_query,
        "application read evidence drifted",
    )


def review_final_state(evidence: Path) -> None:
    final_state = key_value_csv(evidence / "final-state.csv")
    require(
        final_state["release"] == "1.3-proposal"
        and final_state["fixture"] == "ch15-search-v1"
        and final_state["embedding_model"]
        == "pg36-handcrafted-topic-4d-v1"
        and final_state["products"] == "17"
        and final_state["active_products"] == "16"
        and final_state["queries"] == "8"
        and final_state["judgments"] == "24"
        and final_state["business_checksum"]
        == "c637abf09edba88b7793f91201a57c34"
        and final_state["hybrid_top_ids"]
        == (
            "q01=1,2,3;q02=3,2,1;q03=2,1,3;"
            "q04=4,6,5;q05=5,6,4;q06=7,8,9;"
            "q07=10,11,12;q08=12,10,11"
        ),
        "final state drifted",
    )
    verify = read_text(evidence / "verify.txt")
    for line in (
        "status=ok",
        "fixture=17-products/8-queries/24-judgments",
        "quality=exact-golden+precision+recall+mrr+ndcg",
        "ann=measured-separately-from-quality-golden",
        "security=pg36_app-read-only",
        "extensions=ch14-preserved",
    ):
        require(line in verify, f"verify evidence lacks {line}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--fixture-manifest",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    baseline = args.baseline.resolve()
    fixture_manifest = args.fixture_manifest.resolve()
    source_dir = args.source_dir.resolve()

    checksum = review_manifest(
        evidence,
        baseline,
        fixture_manifest,
    )
    review_fixture_sources(
        evidence,
        source_dir,
        fixture_manifest,
    )
    review_catalogs(evidence)
    review_text_search(evidence)
    review_quality(evidence)
    review_ann_and_plans(evidence)
    review_security_failure(evidence)
    review_final_state(evidence)

    print("status=ok")
    print("fixture=frozen-byte-identical")
    print("quality=precision+recall+mrr+ndcg")
    print("ranking=fts+trigram+exact-vector+rrf")
    print("ann=exact-comparison-required")
    print("security=read-only-app")
    print("pigsty_l1=not-run")
    print(f"release_candidate_checksum={checksum}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
