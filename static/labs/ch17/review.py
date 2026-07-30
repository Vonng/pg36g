#!/usr/bin/env python3
"""Review chapter 17 evidence without turning the loopback fixture into a benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "pg36 ch17 analytics fdw lab; safe to rebuild"
BUSINESS_CHECKSUM = "42fb8ab5444469eba1f104a8e1e529dd"
MONTHLY_CHECKSUM = "644d45544ebbc2a80c42270c38ac6885"
FROZEN_SHA256 = (
    "64b045809e10364fd84a587121d919e8562a15335c4c6c015e91a0ead3a44323"
)


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
        and not line.startswith("[remote-context] ")
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
    fixture_manifest_path: Path,
) -> str:
    manifest = read_text(evidence / "manifest.txt")
    baseline_checksum = canonical_checksum(baseline_path)
    fixture_checksum = canonical_checksum(fixture_manifest_path)
    require(
        "database=pg36_shop" in manifest
        and "admin_session_user=postgres" in manifest
        and "in_recovery=false" in manifest
        and "postgres_fdw=1.2" in manifest
        and "shard_databases=pg36_shard_a,pg36_shard_b" in manifest
        and "validation_path=direct-postgresql-loopback-fdw" in manifest
        and "pigsty_reference=4.4" in manifest
        and "pigsty_l1=not-run" in manifest
        and "model_version=ch04-v1" in manifest
        and "fixture=ch17-analytics-v1" in manifest
        and "distribution=explicit-list-by-tenant" in manifest
        and "authentication=lab-only-password_required=false" in manifest
        and f"release_candidate_checksum={baseline_checksum}" in manifest
        and f"fixture_manifest_checksum={fixture_checksum}" in manifest,
        "manifest target, dependency, identity, or warning drifted",
    )
    version = re.search(r"server_version=(\d+)\.", manifest)
    require(
        version is not None and int(version.group(1)) == 18,
        "formal fixture was not captured on PostgreSQL 18.x",
    )
    host = re.search(r"^fdw_host=(.+)$", manifest, re.MULTILINE)
    port = re.search(r"^fdw_port=(\d+)$", manifest, re.MULTILINE)
    require(
        host is not None and host.group(1) and port is not None,
        "manifest did not freeze the loopback endpoint",
    )
    return baseline_checksum


def review_fixture_sources(
    evidence: Path,
    source_dir: Path,
    fixture_manifest_path: Path,
) -> None:
    fixture = load_json(fixture_manifest_path)
    frozen = source_dir / fixture["frozen_export"]["path"]
    require(
        sha256(frozen) == fixture["frozen_export"]["sha256"]
        == FROZEN_SHA256,
        "frozen monthly export hash drifted",
    )
    require(
        len(read_csv(frozen)) == fixture["frozen_export"]["rows"] == 32,
        "frozen monthly export row count drifted",
    )

    for evidence_name in (
        "monthly-local.csv",
        "monthly-summary.csv",
        "monthly-distributed.csv",
        "monthly-two-stage.csv",
    ):
        require(
            read_bytes(evidence / evidence_name) == read_bytes(frozen),
            f"{evidence_name} is not byte-identical to the frozen result",
        )

    for key in ("coordinator", "remote"):
        loader = source_dir / fixture["loaders"][key]["path"]
        require(
            sha256(loader) == fixture["loaders"][key]["sha256"],
            f"{loader.name} hash drifted from fixture manifest",
        )

    require(
        fixture["generator"]
        == {
            "identity": "fixture-generator-v1",
            "tenant_count": 8,
            "accounts_per_tenant": 50,
            "day_count": 120,
            "sales_per_account_day": 5,
            "first_day": "2026-01-01",
            "last_day": "2026-04-30",
            "frozen_at": "2026-07-29T00:00:00Z",
        }
        and fixture["local"]["sales"] == 240000
        and fixture["local"]["business_checksum"] == BUSINESS_CHECKSUM
        and fixture["local"]["monthly_checksum"] == MONTHLY_CHECKSUM
        and fixture["distribution"]["strategy"]
        == "explicit LIST routing by tenant identity"
        and fixture["authentication"]["production_approved"] is False,
        "fixture generator, routing, checksum, or safety identity drifted",
    )


def review_fixture_facts(evidence: Path) -> None:
    facts = key_value_csv(evidence / "fixture-facts.csv")
    require(
        facts
        == {
            "distributed_amount": "2256000.00",
            "distributed_sales": "240000",
            "distributed_units": "1200000",
            "first_day": "2026-01-01",
            "last_day": "2026-04-30",
            "local_amount": "2256000.00",
            "local_sales": "240000",
            "local_units": "1200000",
            "shard_rows": (
                "shop_ch17.sales_fact_dist_0:120000,"
                "shop_ch17.sales_fact_dist_1:120000"
            ),
            "summary_rows": "2880",
            "summary_sales": "240000",
        },
        "coordinator fixture facts drifted",
    )

    remote_a = read_csv(evidence / "remote-a-state.csv")
    remote_b = read_csv(evidence / "remote-b-state.csv")
    require(
        len(remote_a) == 1 and len(remote_b) == 1,
        "remote state evidence did not contain one row per shard",
    )
    a = remote_a[0]
    b = remote_b[0]
    require(
        a
        == {
            "database_name": "pg36_shard_a",
            "shard_remainder": "0",
            "tenant_count": "4",
            "min_tenant": "2",
            "max_tenant": "8",
            "account_count": "200",
            "sale_count": "120000",
            "unit_count": "599988",
            "amount_total": "1188000.00",
            "first_day": "2026-01-01",
            "last_day": "2026-04-30",
            "checksum": "274002669404fbcd449bdecd929624e3",
            "marker": "pg36 ch17 shard 0 lab; safe to rebuild",
        }
        and b
        == {
            "database_name": "pg36_shard_b",
            "shard_remainder": "1",
            "tenant_count": "4",
            "min_tenant": "1",
            "max_tenant": "7",
            "account_count": "200",
            "sale_count": "120000",
            "unit_count": "600012",
            "amount_total": "1068000.00",
            "first_day": "2026-01-01",
            "last_day": "2026-04-30",
            "checksum": "0bb770361058ec76ebc81a2a7d1e2629",
            "marker": "pg36 ch17 shard 1 lab; safe to rebuild",
        },
        "remote cardinality, placement, or checksum drifted",
    )


def review_catalogs(evidence: Path) -> None:
    servers = {
        row["server_name"]: row
        for row in read_csv(evidence / "server-catalog.csv")
    }
    require(
        set(servers) == {"pg36_ch17_shard_a", "pg36_ch17_shard_b"}
        and all(
            row["wrapper_name"] == "postgres_fdw"
            and row["owner"] == "pg36_owner"
            and row["marker"] == MARKER
            and "host=" in row["server_options"]
            and "port=" in row["server_options"]
            and "fetch_size=10000" in row["server_options"]
            for row in servers.values()
        )
        and "dbname=pg36_shard_a"
        in servers["pg36_ch17_shard_a"]["server_options"]
        and "dbname=pg36_shard_b"
        in servers["pg36_ch17_shard_b"]["server_options"],
        "foreign server identity or options drifted",
    )
    require(
        read_bytes(evidence / "server-catalog.csv")
        == read_bytes(evidence / "server-catalog-after-failure.csv"),
        "failed-shard probe did not restore the server catalog exactly",
    )

    mappings = read_csv(evidence / "mapping-catalog.csv")
    expected_mapping_keys = {
        (server, role)
        for server in ("pg36_ch17_shard_a", "pg36_ch17_shard_b")
        for role in ("pg36_app", "pg36_owner", "postgres")
    }
    require(
        len(mappings) == 6
        and {
            (row["server_name"], row["local_user"])
            for row in mappings
        }
        == expected_mapping_keys
        and all(
            "password_required=false" in row["mapping_options"]
            and (
                (
                    row["local_user"] == "pg36_app"
                    and "user=pg36_app" in row["mapping_options"]
                )
                or (
                    row["local_user"] != "pg36_app"
                    and "user=postgres" in row["mapping_options"]
                )
            )
            for row in mappings
        ),
        "user mapping inventory or lab-only auth option drifted",
    )

    relations = read_csv(evidence / "relation-catalog.csv")
    kind_counts: dict[str, int] = {}
    for row in relations:
        kind_counts[row["relkind"]] = kind_counts.get(row["relkind"], 0) + 1
    relation_by_name = {row["relation_name"]: row for row in relations}
    require(
        len(relations) == 18
        and kind_counts
        == {"f": 4, "i": 6, "m": 1, "p": 2, "r": 3, "v": 2}
        and all(
            row["owner"] == "pg36_owner" and row["marker"] == MARKER
            for row in relations
        )
        and relation_by_name["sales_fact_dist_0"]["partition_bound"]
        == "FOR VALUES IN (2, 4, 6, 8)"
        and relation_by_name["sales_fact_dist_1"]["partition_bound"]
        == "FOR VALUES IN (1, 3, 5, 7)"
        and relation_by_name["sales_fact_dist_0"]["foreign_server"]
        == "pg36_ch17_shard_a"
        and relation_by_name["sales_fact_dist_1"]["foreign_server"]
        == "pg36_ch17_shard_b",
        "managed relation inventory or explicit LIST routing drifted",
    )

    indexes = {
        row["index_name"]: row
        for row in read_csv(evidence / "index-catalog.csv")
    }
    require(
        len(indexes) == 6
        and indexes["sales_fact_day_brin_idx"]["access_method"] == "brin"
        and indexes["sales_fact_day_brin_idx"]["operator_classes"]
        == "pg_catalog.date_minmax_ops"
        and indexes["sales_fact_tenant_day_idx"]["access_method"] == "btree"
        and indexes["sales_fact_tenant_day_idx"]["operator_classes"]
        == (
            "pg_catalog.int4_ops,pg_catalog.date_ops,"
            "pg_catalog.int4_ops"
        )
        and all(
            row["is_valid"] == "t"
            and row["is_ready"] == "t"
            and row["is_live"] == "t"
            and int(row["index_bytes"]) > 0
            and row["marker"] == MARKER
            for row in indexes.values()
        ),
        "managed index inventory or operator class drifted",
    )

    security = key_value_csv(evidence / "security-catalog.csv")
    require(
        security
        == {
            "app_distributed_sales_select": "true",
            "app_distributed_sales_write": "false",
            "app_local_sales_select": "true",
            "app_local_sales_write": "false",
            "app_schema_usage": "true",
            "app_server_a_usage": "true",
            "app_server_b_usage": "true",
        },
        "application privilege boundary drifted",
    )

    sizes = {
        row["object_name"]: int(row["bytes"])
        for row in read_csv(evidence / "size-catalog.csv")
    }
    require(
        set(sizes)
        == {
            "account_dim_total",
            "daily_summary_total",
            "sales_day_brin_index",
            "sales_fact_heap",
            "sales_fact_total",
            "sales_tenant_day_index",
        }
        and all(value > 0 for value in sizes.values())
        and sizes["sales_fact_total"] > sizes["sales_fact_heap"]
        and sizes["sales_day_brin_index"]
        < sizes["sales_tenant_day_index"],
        "size evidence is missing, impossible, or no longer comparable",
    )


def review_plans(evidence: Path) -> None:
    parallel = read_text(evidence / "local-parallel-plan.txt")
    spill_low = read_text(evidence / "spill-low-plan.txt")
    spill_high = read_text(evidence / "spill-high-plan.txt")
    selective = read_text(evidence / "selective-index-plan.txt")
    raw = read_text(evidence / "raw-aggregate-plan.txt")
    summary = read_text(evidence / "summary-aggregate-plan.txt")
    pruned = read_text(evidence / "tenant-pruned-plan.txt")
    naive = read_text(evidence / "distributed-naive-plan.txt")
    two_stage = read_text(evidence / "distributed-two-stage-plan.txt")
    collocated = read_text(evidence / "collocated-parent-plan.txt")

    require(
        "Workers Planned: 2" in parallel
        and "Workers Launched: 2" in parallel
        and "Parallel Seq Scan on sales_fact" in parallel
        and "Partial HashAggregate" in parallel
        and "Finalize HashAggregate" in parallel
        and "actual rows=32" in parallel,
        "parallel aggregate plan drifted",
    )
    require(
        "actual rows=240000" in spill_low
        and "Sort Method: external merge" in spill_low
        and "Disk:" in spill_low
        and "temp read=" in spill_low
        and "actual rows=240000" in spill_high
        and "Sort Method: quicksort" in spill_high
        and "Memory:" in spill_high
        and "external merge" not in spill_high
        and "temp read=" not in spill_high,
        "low/high work_mem spill counterexample drifted",
    )
    require(
        "Index Only Scan using sales_fact_tenant_day_idx" in selective
        and "actual rows=7500" in selective
        and "Heap Fetches: 0" in selective
        and "tenant_id = 3" in selective
        and "2026-04-01" in selective,
        "selective covering-index plan drifted",
    )
    require(
        "Parallel Seq Scan on sales_fact" in raw
        and "actual rows=80000" in raw
        and "loops=3" in raw
        and "Seq Scan on daily_tenant_summary" in summary
        and "actual rows=2880" in summary
        and "actual rows=32" in raw
        and "actual rows=32" in summary,
        "raw-versus-summary scan shape drifted",
    )
    require(
        "sales_fact_dist_1" in pruned
        and "sales_fact_dist_0" not in pruned
        and "actual rows=7500" in pruned
        and "Remote SQL:" in pruned
        and "tenant_id = 3" in pruned
        and "occurred_on >= '2026-04-01'" in pruned,
        "tenant pruning or remote filter pushdown drifted",
    )
    require(
        "Append (actual rows=240000" in naive
        and naive.count("actual rows=120000") == 2
        and "GROUP BY" not in "\n".join(
            line
            for line in naive.splitlines()
            if "Remote SQL:" in line
        ),
        "naive distributed transfer shape drifted",
    )
    require(
        "Append (actual rows=960" in two_stage
        and two_stage.count("actual rows=480") == 2
        and two_stage.count("Remote SQL:") == 2
        and two_stage.count("GROUP BY 1, 2") == 2,
        "two-stage remote aggregation shape drifted",
    )
    require(
        "Hash Join (actual rows=7500" in collocated
        and "Foreign Scan on shop_ch17.sales_fact_dist_1" in collocated
        and "actual rows=7500" in collocated
        and "Foreign Scan on shop_ch17.account_dim_dist_1" in collocated
        and "actual rows=50" in collocated
        and collocated.count("Remote SQL:") == 2,
        "collocated-but-not-pushed join counterexample drifted",
    )


def review_boundaries_and_final(evidence: Path) -> None:
    app_rows = read_csv(evidence / "app-query.csv")
    require(
        app_rows
        == [{"sale_count": "7500", "amount_total": "69375.00"}],
        "application read path drifted",
    )

    for name, sqlstate in (
        ("app-write", "42501"),
        ("shard-failure", "08001"),
    ):
        require(
            read_text(evidence / f"{name}.exit").strip() == "exit=3"
            and sqlstate in read_text(evidence / f"{name}.stderr"),
            f"{name} did not preserve SQLSTATE {sqlstate}",
        )
    require(
        "healthy_shard_tenant_2=30000"
        in read_text(evidence / "shard-failure.stdout"),
        "failed-shard probe lost the healthy shard read",
    )

    final = key_value_csv(evidence / "final-state.csv")
    require(
        final
        == {
            "business_checksum": BUSINESS_CHECKSUM,
            "distributed_sales": "240000",
            "fixture": "ch17-analytics-v1",
            "local_sales": "240000",
            "monthly_checksum": MONTHLY_CHECKSUM,
            "naive_transfer_rows": "240000",
            "postgres_fdw": "1.2",
            "release": "1.5-proposal",
            "shard_rows": (
                "shop_ch17.sales_fact_dist_0:120000,"
                "shop_ch17.sales_fact_dist_1:120000"
            ),
            "summary_rows": "2880",
            "tenant3_april": "7500:69375.00",
            "two_stage_transfer_rows": "960",
        },
        "final state or business checksum drifted",
    )

    verification = read_text(evidence / "verify.txt")
    remote_a = read_text(evidence / "remote-a-verify.txt")
    remote_b = read_text(evidence / "remote-b-verify.txt")
    require(
        "status=ok" in verification
        and "fixture=generator-v1" in verification
        and "single_node=parallel+index+summary+spill" in verification
        and "distributed=tenant-pruning+fdw+two-stage" in verification
        and f"monthly_checksum={MONTHLY_CHECKSUM}" in verification
        and f"business_checksum={BUSINESS_CHECKSUM}" in verification
        and "status=remote-ok" in remote_a
        and "database=pg36_shard_a" in remote_a
        and "remainder=0" in remote_a
        and "sales=120000" in remote_a
        and "status=remote-ok" in remote_b
        and "database=pg36_shard_b" in remote_b
        and "remainder=1" in remote_b
        and "sales=120000" in remote_b,
        "coordinator or remote database verification did not finish cleanly",
    )


def review_baseline(path: Path) -> None:
    baseline = load_json(path)
    require(
        baseline["release"] == "1.5-proposal"
        and baseline["fixture"] == "ch17-analytics-v1"
        and baseline["target"]["validated_on"] == "18.4"
        and baseline["target"]["postgres_fdw"] == "1.2"
        and baseline["target"]["pigsty_l1_validation"] == "not-run"
        and baseline["decision"]["default_path"]
        == "prove and exhaust the single-node boundary before distributing"
        and baseline["decision"]["distribution_key"] == "tenant_id"
        and "not tenant_id modulo 2"
        in baseline["decision"]["hash_partition_warning"]
        and baseline["decision"]["production_sharding_candidate"]
        == (
            "evaluate Citus only after workload, ownership, "
            "availability, and operations gates pass"
        )
        and baseline["contracts"]["local_sales"] == 240000
        and baseline["contracts"]["naive_transfer_rows"] == 240000
        and baseline["contracts"]["two_stage_transfer_rows"] == 960
        and baseline["contracts"]["managed_relations"] == 18
        and baseline["contracts"]["user_mappings"] == 6
        and baseline["expected_state"]["business_checksum"]
        == BUSINESS_CHECKSUM
        and baseline["expected_state"]["monthly_checksum"]
        == MONTHLY_CHECKSUM
        and baseline["authentication"]["no_public_mapping"] is True
        and baseline["rollback"]["uses_cascade"] is False
        and baseline["rollback"]["cross_database_atomic"] is False
        and baseline["rollback"]["retains_database_shells"] is True,
        "release proposal drifted from the reviewed architecture contract",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--fixture-manifest", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    args = parser.parse_args()

    baseline_checksum = review_manifest(
        args.evidence,
        args.baseline,
        args.fixture_manifest,
    )
    review_fixture_sources(
        args.evidence,
        args.source_dir,
        args.fixture_manifest,
    )
    review_fixture_facts(args.evidence)
    review_catalogs(args.evidence)
    review_plans(args.evidence)
    review_boundaries_and_final(args.evidence)
    review_baseline(args.baseline)

    print("status=review-ok")
    print("fixture=frozen-byte-identical-four-paths")
    print("single_node=parallel+index+summary+spill")
    print("distributed=tenant-pruning+fdw+two-stage")
    print("counterexamples=hash-is-not-modulo+join-not-pushed")
    print("failure=healthy-shard-read+global-08001")
    print(f"business_checksum={BUSINESS_CHECKSUM}")
    print(f"monthly_checksum={MONTHLY_CHECKSUM}")
    print(f"release_candidate_checksum={baseline_checksum}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
