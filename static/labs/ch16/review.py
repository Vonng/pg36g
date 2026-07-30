#!/usr/bin/env python3
"""Review chapter 16 evidence without treating the tiny fixture as a benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "pg36 ch16 spatiotemporal lab; safe to rebuild"
CHECKSUM = "53f51cef1f0bed1a5c2fc89bfad109f4"


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
        and "extension_versions=btree_gist:1.8,postgis:3.6.4"
        in manifest
        and "preserved_ch14_extensions=pg_trgm:1.6,vector:0.8.4"
        in manifest
        and "partition_timezone=UTC" in manifest
        and "coordinate_contract=EPSG:4326-synthetic" in manifest
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
    fixture = load_json(fixture_manifest_path)
    pairs = (
        ("attempts", "frozen-attempts.csv", "attempts.csv"),
        ("geofences", "frozen-geofences.csv", "geofences.csv"),
        ("hubs", "frozen-hubs.csv", "hubs.csv"),
    )
    for key, source_name, evidence_name in pairs:
        source = source_dir / source_name
        exported = evidence / evidence_name
        require(
            read_bytes(source) == read_bytes(exported),
            f"{evidence_name} is not a byte-identical database export",
        )
        require(
            sha256(source) == fixture[key]["sha256"],
            f"{source_name} hash drifted from fixture manifest",
        )
        require(
            len(read_csv(source)) == fixture[key]["rows"],
            f"{source_name} row count drifted",
        )

    loader = source_dir / fixture["loader"]["path"]
    require(
        sha256(loader) == fixture["loader"]["sha256"],
        "fixture.sql hash drifted from fixture manifest",
    )
    require(
        fixture["time"]
        == {
            "event_time": "occurred_at",
            "ingest_time": "received_at",
            "valid_time": "valid_during",
            "storage_timezone": "UTC",
            "display_timezone_probe": "America/New_York",
            "range_bounds": "[)",
        }
        and fixture["space"]["srid"] == 4326
        and fixture["space"]["external_geodata"] is False,
        "fixture time or coordinate identity drifted",
    )


def review_time(evidence: Path) -> None:
    temporal = key_value_csv(evidence / "temporal-analysis.csv")
    require(
        temporal
        == {
            "dst_e002_local": "2026-03-08 01:55:00",
            "dst_e003_local": "2026-03-08 03:05:00",
            "dst_elapsed_seconds": "600",
            "duplicate_event": "e003:2",
            "late_event_ids": "e001,e004",
            "out_of_order_pair": "e004->e005",
            "partition_boundary": (
                "e008=shop_ch16.delivery_event_20260308;"
                "e009=shop_ch16.delivery_event_20260309"
            ),
            "utc_day8_events": "7",
        },
        "temporal facts drifted",
    )

    partitions = read_csv(evidence / "partition-catalog.csv")
    require(
        len(partitions) == 3
        and {
            row["partition_name"]: int(row["event_count"])
            for row in partitions
        }
        == {
            "delivery_event_20260307": 1,
            "delivery_event_20260308": 7,
            "delivery_event_20260309": 4,
        }
        and all(
            row["owner"] == "pg36_owner"
            and row["marker"] == MARKER
            and row["partition_bound"].startswith("FOR VALUES FROM")
            for row in partitions
        ),
        "partition catalog drifted",
    )

    buckets = read_csv(evidence / "time-buckets.csv")
    require(
        len(buckets) == 11
        and sum(int(row["event_count"]) for row in buckets) == 12
        and sum(int(row["late_event_count"]) for row in buckets) == 2
        and next(
            row
            for row in buckets
            if row["bucket_start"] == "2026-03-08T12:00:00Z"
        )["event_count"]
        == "2",
        "time bucket evidence drifted",
    )


def review_space(evidence: Path) -> None:
    memberships = read_csv(evidence / "zone-membership.csv")
    actual_memberships = [
        (
            row["event_id"],
            row["zone_id"],
            int(row["zone_version"]),
        )
        for row in memberships
    ]
    expected_memberships = [
        ("e001", "central", 1),
        ("e002", "central", 1),
        ("e003", "central", 1),
        ("e003", "east", 1),
        ("e004", "east", 1),
        ("e005", "central", 2),
        ("e005", "east", 1),
        ("e006", "central", 2),
        ("e006", "east", 1),
        ("e007", "airport", 1),
        ("e008", "central", 2),
        ("e009", "central", 2),
        ("e011", "east", 1),
        ("e012", "airport", 1),
    ]
    require(
        actual_memberships == expected_memberships,
        "zone membership evidence drifted",
    )

    boundaries = {
        (
            row["scenario"],
            row["event_id"],
            row["zone_id"],
        ): (row["covers"], row["contains"], row["touches"])
        for row in read_csv(evidence / "boundary-semantics.csv")
    }
    require(
        boundaries
        == {
            ("at_expansion", "e005", "central"): ("t", "t", "f"),
            ("before_expansion", "e004", "central"): (
                "f",
                "f",
                "f",
            ),
            ("shared_boundary", "e003", "central"): (
                "t",
                "f",
                "t",
            ),
            ("shared_boundary", "e003", "east"): ("t", "f", "t"),
        },
        "boundary predicate evidence drifted",
    )

    distances = {
        row["hub_id"]: row
        for row in read_csv(evidence / "distance-semantics.csv")
    }
    require(
        set(distances) == {"airport", "central", "east"}
        and distances["airport"]["nearest_event_id"] == "e007"
        and distances["central"]["nearest_event_id"] == "e001"
        and distances["east"]["nearest_event_id"] == "e004"
        and all(row["within_1km"] == "t" for row in distances.values())
        and all(int(row["distance_meters"]) >= 0 for row in distances.values()),
        "distance or nearest-event evidence drifted",
    )


def review_catalogs(evidence: Path) -> None:
    extensions = {
        row["extension_name"]: row
        for row in read_csv(evidence / "extension-catalog.csv")
    }
    require(
        set(extensions) == {"btree_gist", "postgis"}
        and extensions["btree_gist"]["extension_version"] == "1.8"
        and extensions["btree_gist"]["schema_name"]
        == "shop_ch16_ext"
        and extensions["btree_gist"]["owner"] == "pg36_owner"
        and extensions["btree_gist"]["relocatable"] == "t"
        and extensions["btree_gist"]["trusted"] == "t"
        and extensions["postgis"]["extension_version"] == "3.6.4"
        and extensions["postgis"]["schema_name"] == "shop_ch16_ext"
        and extensions["postgis"]["relocatable"] == "f"
        and extensions["postgis"]["trusted"] == "f"
        and all(row["marker"] == MARKER for row in extensions.values()),
        "extension catalog drifted",
    )

    indexes = {
        row["index_name"]: row
        for row in read_csv(evidence / "index-catalog.csv")
    }
    require(
        len(indexes) == 13
        and indexes["delivery_hub_location_spgist_idx"]["access_method"]
        == "spgist"
        and indexes["delivery_hub_location_spgist_idx"][
            "operator_classes"
        ]
        == "shop_ch16_ext.spgist_geometry_ops_2d"
        and indexes["geofence_version_no_overlap"]["access_method"]
        == "gist"
        and indexes["geofence_version_no_overlap"]["operator_classes"]
        == "shop_ch16_ext.gist_text_ops,pg_catalog.range_ops"
        and all(
            row["is_valid"] == "t"
            and row["is_ready"] == "t"
            and row["is_live"] == "t"
            and int(row["index_bytes"]) > 0
            and row["marker"] == MARKER
            for row in indexes.values()
        )
        and sum(
            row["operator_classes"]
            == "shop_ch16_ext.gist_geography_ops"
            for row in indexes.values()
        )
        == 3
        and sum(
            row["operator_classes"]
            == "shop_ch16_ext.gist_geometry_ops_2d"
            for row in indexes.values()
        )
        == 4,
        "managed index inventory drifted",
    )

    security = key_value_csv(evidence / "security-catalog.csv")
    require(
        security
        == {
            "app_event_delete": "false",
            "app_event_insert": "false",
            "app_event_select": "true",
            "app_event_update": "false",
            "app_extension_schema_usage": "true",
            "app_membership_select": "true",
            "app_schema_usage": "true",
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
            "delivery_event_parent_total",
            "delivery_event_partitions_total",
            "geofence_total",
            "hub_total",
            "ingest_total",
        }
        and sizes["delivery_event_parent_total"] == 0
        and all(
            value > 0
            for key, value in sizes.items()
            if key != "delivery_event_parent_total"
        ),
        "relation size evidence drifted",
    )


def review_plans(evidence: Path) -> None:
    direct = read_text(evidence / "time-pruned-plan.txt")
    wrapped = read_text(evidence / "time-wrapped-plan.txt")
    gist = read_text(evidence / "spatial-gist-plan.txt")
    spgist = read_text(evidence / "spatial-spgist-plan.txt")
    joint = read_text(evidence / "joint-plan.txt")

    require(
        "delivery_event_20260308" in direct
        and "delivery_event_20260307" not in direct
        and "delivery_event_20260309" not in direct
        and "Append" not in direct,
        "direct time predicate did not prove static partition pruning",
    )
    require(
        "Append" in wrapped
        and all(
            name in wrapped
            for name in (
                "delivery_event_20260307",
                "delivery_event_20260308",
                "delivery_event_20260309",
            )
        ),
        "wrapped partition-key counterexample drifted",
    )
    require(
        "event_20260308_geog_gist_idx" in gist
        and "st_dwithin" in gist.lower()
        and "delivery_event_20260307" not in gist
        and "delivery_event_20260309" not in gist,
        "geography GiST plan drifted",
    )
    require(
        "delivery_hub_location_spgist_idx" in spgist
        and "st_dwithin" in spgist.lower(),
        "SP-GiST path evidence drifted",
    )
    require(
        "geofence_version_no_overlap" in joint
        and "event_20260308_location_gist_idx" in joint
        and "st_covers" in joint.lower()
        and "delivery_event_20260307" not in joint
        and "delivery_event_20260309" not in joint,
        "joint time-space plan drifted",
    )


def review_boundaries_and_final(evidence: Path) -> None:
    app_rows = read_csv(evidence / "app-query.csv")
    require(
        [row["event_id"] for row in app_rows]
        == ["e002", "e003", "e005", "e006", "e008"]
        and all(row["zone_id"] == "central" for row in app_rows),
        "application read path drifted",
    )

    for name, sqlstate in (
        ("srid-mismatch", "XX000"),
        ("overlap-geofence", "23P01"),
        ("app-write", "42501"),
    ):
        require(
            read_text(evidence / f"{name}.exit").strip() == "exit=3"
            and sqlstate in read_text(evidence / f"{name}.stderr"),
            f"{name} did not preserve the expected failure boundary",
        )

    final = key_value_csv(evidence / "final-state.csv")
    require(
        final
        == {
            "attempts": "13",
            "business_checksum": CHECKSUM,
            "central_day8": "e002,e003,e005,e006,e008",
            "duplicate_registry": "e003:2",
            "events": "12",
            "extensions": "btree_gist:1.8,postgis:3.6.4",
            "fixture": "ch16-spatiotemporal-v1",
            "late_events": "e001,e004",
            "memberships": "14",
            "partition_counts": (
                "shop_ch16.delivery_event_20260307:1,"
                "shop_ch16.delivery_event_20260308:7,"
                "shop_ch16.delivery_event_20260309:4"
            ),
            "release": "1.4-proposal",
        },
        "final state or business checksum drifted",
    )

    verification = read_text(evidence / "verify.txt")
    require(
        "status=ok" in verification
        and "fixture=frozen-byte-identical" in verification
        and f"business_checksum={CHECKSUM}" in verification,
        "database verification did not finish cleanly",
    )


def review_baseline(path: Path) -> None:
    baseline = load_json(path)
    require(
        baseline["release"] == "1.4-proposal"
        and baseline["fixture"] == "ch16-spatiotemporal-v1"
        and baseline["target"]["validated_on"] == "18.4"
        and baseline["target"]["postgis"] == "3.6.4"
        and baseline["decision"]["partition_key"] == "occurred_at"
        and baseline["decision"]["partition_timezone"] == "UTC"
        and baseline["decision"]["canonical_srid"] == 4326
        and baseline["contracts"]["ingest_attempts"] == 13
        and baseline["contracts"]["distinct_events"] == 12
        and baseline["contracts"]["zone_memberships"] == 14
        and baseline["expected_state"]["business_checksum"] == CHECKSUM
        and baseline["rollback"]["uses_cascade"] is False
        and baseline["rollback"]["transactional"] is True,
        "release proposal drifted from the reviewed contract",
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
    review_time(args.evidence)
    review_space(args.evidence)
    review_catalogs(args.evidence)
    review_plans(args.evidence)
    review_boundaries_and_final(args.evidence)
    review_baseline(args.baseline)

    print("status=review-ok")
    print("fixture=frozen-byte-identical")
    print("time=event+ingest+validity+dst")
    print("space=geometry+geography+srid+boundary")
    print("plans=pruning+gist+spgist+joint")
    print(f"business_checksum={CHECKSUM}")
    print(f"release_candidate_checksum={baseline_checksum}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
