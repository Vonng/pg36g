#!/usr/bin/env python3
"""Validate chapter 26 contracts, evidence, and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SOURCE_NAMES = [
    "requirements.json",
    "workload-contract.json",
    "experiment-matrix.json",
    "capacity-model.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "reset-cell.sql",
    "read-product.sql",
    "read-order.sql",
    "place-order.sql",
    "stat-snapshot.sql",
    "wait-sampler.sql",
    "system_sampler.py",
    "remote_benchmark.py",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]


class ValidationFailure(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--capacity", type=Path)
    parser.add_argument("--cleanup", type=Path)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--negative-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, code: str, message: str, errors: list[dict[str, str]]) -> None:
    if not condition:
        errors.append({"code": code, "message": message})


def validate_contracts(
    requirements: dict[str, Any],
    workload: dict[str, Any],
    matrix: dict[str, Any],
    model: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    target = requirements.get("target", {})
    require(
        target.get("production_data") is False
        and target.get("production_traffic") is False
        and target.get("production_slo_claimed") is False,
        "TARGET_NOT_DISPOSABLE",
        "target must prohibit production data, traffic, and SLO claims",
        errors,
    )
    require(
        target.get("database") == "pg36_capacity"
        and target.get("benchmark_role") == "dbuser_pg36bench",
        "FIXTURE_SCOPE_DRIFT",
        "fixture database or role drifted",
        errors,
    )
    require(
        target.get("client_host") == "pg-meta-1"
        and target.get("primary_host") == "pg-test-1"
        and target.get("client_host") != target.get("primary_host"),
        "CLIENT_PATH_DRIFT",
        "client and server identity must remain distinct",
        errors,
    )
    prohibited = set(requirements.get("risk", {}).get("prohibited_actions", []))
    required_prohibitions = {
        "reset PostgreSQL, pg_stat_statements, operating-system, or monitoring statistics",
        "drop operating-system caches, restart a service, checkpoint on demand, or fail over",
        "disable durability, archive, replication, checksums, constraints, or synchronous_commit",
    }
    require(
        required_prohibitions <= prohibited,
        "SAFETY_BOUNDARY_DRIFT",
        "one or more required safety prohibitions are missing",
        errors,
    )
    unsupported = set(
        requirements.get("purpose", {}).get("unsupported_claims", [])
    )
    require(
        "universal PostgreSQL performance" in unsupported
        and "production sizing or production SLO acceptance" in unsupported,
        "CLAIM_BOUNDARY_DRIFT",
        "universal and production claim boundaries must remain explicit",
        errors,
    )
    semantics = workload.get("semantics", {})
    require(
        semantics.get("mode") == "closed-loop-maximum-throughput-probe"
        and semantics.get("think_time_ms") == 0
        and semantics.get("connection_lifetime")
        == "persistent for each client during one run"
        and semantics.get("query_protocol") == "prepared"
        and semantics.get("latency_limit_ms") == 250,
        "WORKLOAD_SEMANTICS_DRIFT",
        "workload execution semantics drifted",
        errors,
    )
    durability = semantics.get("durability", {})
    require(
        durability.get("synchronous_commit") == "on"
        and durability.get("unlogged_tables") is False
        and durability.get("fsync_override") is False,
        "DURABILITY_DRIFT",
        "durability controls drifted",
        errors,
    )
    mix = workload.get("transaction_mix", [])
    mix_by_id = {row.get("id"): row for row in mix}
    require(
        set(mix_by_id) == {"read-product", "read-order", "place-order"}
        and sum(row.get("weight", 0) for row in mix) == 100
        and mix_by_id.get("read-product", {}).get("weight") == 50
        and mix_by_id.get("read-order", {}).get("weight") == 30
        and mix_by_id.get("place-order", {}).get("weight") == 20,
        "MIX_DRIFT",
        "transaction mix must remain 50/30/20",
        errors,
    )
    scales = workload.get("data_model", {}).get("scales", [])
    require(
        [(row.get("id"), row.get("factor")) for row in scales]
        == [("S", 1), ("M", 8), ("L", 32)],
        "SCALE_DRIFT",
        "dataset scales must remain S=1, M=8, L=32",
        errors,
    )
    controls = workload.get("controls", {})
    require(
        controls.get("repetitions") == 5
        and len(controls.get("concurrency_order_by_repetition", [])) == 5,
        "REPETITION_DRIFT",
        "five repetitions and five counterbalanced orders are required",
        errors,
    )
    require(
        controls.get("concurrency_levels") == [1, 8],
        "CONCURRENCY_DRIFT",
        "concurrency levels must remain one and eight",
        errors,
    )
    require(
        isinstance(controls.get("base_seed"), int)
        and controls.get("seed_formula")
        == "base_seed + scale_factor * 100 + concurrency * 10 + repetition",
        "SEED_DRIFT",
        "deterministic seed contract is missing",
        errors,
    )
    require(
        controls.get("cache_policy")
        == "warm naturally; never drop OS cache or restart PostgreSQL",
        "CACHE_CLAIM_DRIFT",
        "cache policy must remain warm-only",
        errors,
    )
    interpretation = workload.get("interpretation", {})
    require(
        "Two concurrency levels can only bracket a knee"
        in interpretation.get("knee_rule", ""),
        "INTERPRETATION_DRIFT",
        "two points may only bracket a knee",
        errors,
    )
    require(
        interpretation.get("percentile_rule")
        == "Quantiles are computed from transaction samples; quantiles are never averaged.",
        "INTERPRETATION_DRIFT",
        "quantiles must not be averaged",
        errors,
    )
    cells = matrix.get("cells", [])
    require(
        len(cells) == 6
        and {
            (row.get("scale_id"), row.get("clients")) for row in cells
        }
        == {
            ("S", 1),
            ("S", 8),
            ("M", 1),
            ("M", 8),
            ("L", 1),
            ("L", 8),
        }
        and len(matrix.get("run_order", [])) == 30,
        "MATRIX_DRIFT",
        "matrix must contain six cells and thirty runs",
        errors,
    )
    responses = set(matrix.get("responses", []))
    require(
        {
            "tps",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "server_cpu_busy_ratio",
            "wal_bytes",
            "wait_sample_distribution",
        }
        <= responses,
        "RESPONSE_DRIFT",
        "required response variables are missing",
        errors,
    )
    policy = model.get("policy_defaults", {})
    require(
        policy.get("production_numbers_approved") is False,
        "PRODUCTION_CLAIM_DRIFT",
        "production numbers must remain unapproved",
        errors,
    )
    require(
        policy.get("target_cpu_utilization") == 0.65
        and policy.get("minimum_failure_headroom_ratio", 0) >= 0.30,
        "HEADROOM_POLICY_DRIFT",
        "headroom policy drifted",
        errors,
    )
    return errors


def path_parent(document: Any, path: str) -> tuple[Any, str]:
    parts = path.split(".")
    current = document
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current, parts[-1]


def mutate(document: Any, case: dict[str, Any]) -> Any:
    value = copy.deepcopy(document)
    parent, leaf = path_parent(value, case["path"])
    key: Any = int(leaf) if isinstance(parent, list) else leaf
    operation = case["operation"]
    if operation == "set":
        parent[key] = case["value"]
    elif operation == "delete":
        del parent[key]
    elif operation == "delete_value":
        container = parent[key]
        if not isinstance(container, list):
            raise ValidationFailure(
                f"delete_value target is not a list: {case['path']}"
            )
        container.remove(case["value"])
    else:
        raise ValidationFailure(f"unknown mutation operation: {operation}")
    return value


def validate_negative(
    documents: dict[str, Any],
    cases: dict[str, Any],
) -> dict[str, Any]:
    results = []
    for case in cases.get("cases", []):
        mutated = {
            key: copy.deepcopy(value) for key, value in documents.items()
        }
        mutated[case["document"]] = mutate(
            mutated[case["document"]],
            case,
        )
        errors = validate_contracts(
            mutated["requirements"],
            mutated["workload"],
            mutated["matrix"],
            mutated["model"],
        )
        codes = {row["code"] for row in errors}
        passed = case["expected_error"] in codes
        results.append(
            {
                "id": case["id"],
                "expected_error": case["expected_error"],
                "observed_errors": sorted(codes),
                "rejected": passed,
            }
        )
    failed = [row["id"] for row in results if not row["rejected"]]
    if failed:
        raise ValidationFailure(f"negative cases escaped validation: {failed}")
    return {
        "schema": "pg36-ch26-negative-report-v1",
        "cases": len(results),
        "rejected": len(results),
        "results": results,
    }


def source_hashes(source_dir: Path) -> dict[str, str]:
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    if missing:
        raise ValidationFailure(f"source bundle is incomplete: {missing}")
    return {name: sha256(source_dir / name) for name in SOURCE_NAMES}


def validate_preflight(
    preflight: dict[str, Any],
    expected_hashes: dict[str, str],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    live = preflight.get("live", {})
    pg = live.get("postgresql", {})
    require(
        preflight.get("schema") == "pg36-ch26-preflight-evidence-v1"
        and preflight.get("mutation") == "none"
        and preflight.get("source_hashes") == expected_hashes,
        "PREFLIGHT_BINDING_FAILED",
        "preflight schema, mutation, or source hash binding failed",
        errors,
    )
    require(
        live.get("client", {}).get("hostname") == "pg-meta-1"
        and live.get("server", {}).get("hostname") == "pg-test-1"
        and pg.get("cluster_name") == "pg-test"
        and pg.get("in_recovery") is False
        and pg.get("replica_count") == 2,
        "PREFLIGHT_IDENTITY_FAILED",
        "preflight live identity failed",
        errors,
    )
    require(
        preflight.get("clean_start")
        == {"database_absent": True, "role_absent": True},
        "PREFLIGHT_NOT_CLEAN",
        "preflight did not prove a clean start",
        errors,
    )
    require(
        preflight.get("upstream", {})
        .get("chapter_25", {})
        .get("production_ch25_gate")
        == "pending"
        and preflight.get("production_ch26_gate") == "pending",
        "UPSTREAM_GATE_DRIFT",
        "upstream or chapter production gate drifted",
        errors,
    )
    return errors


def validate_capacity(
    capacity: dict[str, Any],
    expected_hashes: dict[str, str],
    workload: dict[str, Any],
    matrix: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    require(
        capacity.get("schema") == "pg36-ch26-capacity-evidence-v1"
        and capacity.get("status") == "passed"
        and capacity.get("source_hashes") == expected_hashes,
        "EVIDENCE_BINDING_FAILED",
        "capacity evidence schema, status, or source hashes failed",
        errors,
    )
    require(
        capacity.get("target", {}).get("production_data") is False
        and capacity.get("target", {}).get("production_traffic") is False,
        "EVIDENCE_TARGET_UNSAFE",
        "capacity evidence target is not disposable",
        errors,
    )
    environment = capacity.get("environment", {})
    require(
        environment.get("client", {}).get("hostname") == "pg-meta-1"
        and environment.get("server", {}).get("hostname") == "pg-test-1"
        and environment.get("connection_path", {}).get("mode")
        == "direct-primary"
        and environment.get("connection_path", {}).get(
            "client_and_server_are_distinct_hosts"
        )
        is True,
        "EVIDENCE_PATH_DRIFT",
        "measured connection path drifted",
        errors,
    )
    identity = capacity.get("benchmark_identity", {})
    require(
        identity.get("database") == "pg36_capacity"
        and identity.get("user") == "dbuser_pg36bench"
        and identity.get("superuser") is False
        and identity.get("in_recovery") is False,
        "EVIDENCE_ROLE_DRIFT",
        "benchmark database, role, privilege, or server role drifted",
        errors,
    )
    require(
        identity.get("hba_membership")
        == {
            "role": "dbrole_readwrite",
            "inherit": False,
            "set": False,
            "readonly_member": True,
        },
        "EVIDENCE_HBA_MEMBERSHIP_DRIFT",
        "temporary HBA group membership is missing or grants inheritance",
        errors,
    )
    experiment = capacity.get("experiment", {})
    runs = experiment.get("runs", [])
    expected_order = matrix.get("run_order", [])
    require(
        experiment.get("measured_runs") == 30
        and experiment.get("cells") == 6
        and experiment.get("repetitions_per_cell") == 5
        and experiment.get("run_order") == expected_order
        and len(runs) == 30,
        "EVIDENCE_MATRIX_INCOMPLETE",
        "capacity evidence does not contain the exact 30-run matrix",
        errors,
    )
    scale_by_id = {
        row["id"]: row
        for row in workload.get("data_model", {}).get("scales", [])
    }
    expected_counter: Counter[tuple[str, int]] = Counter()
    for run in runs:
        scale = scale_by_id.get(run.get("scale_id"), {})
        expected_seed = (
            workload["controls"]["base_seed"]
            + scale.get("factor", -100000) * 100
            + run.get("clients", -1000) * 10
            + run.get("repetition", -100)
        )
        expected_counter[(run.get("scale_id"), run.get("clients"))] += 1
        pgbench = run.get("pgbench", {})
        log = run.get("transaction_log", {})
        latency = log.get("latency_ms", {})
        reset = run.get("stat_delta", {}).get("stats_reset_unchanged", {})
        require(
            run.get("seed") == expected_seed
            and run.get("measured_seconds")
            >= workload["controls"]["measured_seconds"],
            "EVIDENCE_SEED_OR_DURATION",
            f"{run.get('run_id')} seed or duration drifted",
            errors,
        )
        require(
            pgbench.get("failed_transactions") == 0
            and log.get("failures") == 0
            and log.get("skipped") == 0
            and pgbench.get("processed_transactions") == log.get("transactions")
            and pgbench.get("processed_transactions", 0) > 0,
            "EVIDENCE_TRANSACTION_FAILURE",
            f"{run.get('run_id')} contains a failure, skip, or count mismatch",
            errors,
        )
        require(
            all(
                isinstance(latency.get(key), (int, float))
                for key in ("p50", "p95", "p99", "max")
            )
            and 0
            <= latency.get("p50", -1)
            <= latency.get("p95", -1)
            <= latency.get("p99", -1)
            <= latency.get("max", -1),
            "EVIDENCE_LATENCY_INVALID",
            f"{run.get('run_id')} latency distribution is invalid",
            errors,
        )
        require(
            set(log.get("script_counts", {}))
            == {"read-product", "read-order", "place-order"},
            "EVIDENCE_MIX_MISSING",
            f"{run.get('run_id')} is missing a transaction class",
            errors,
        )
        require(
            reset
            and all(value is True for value in reset.values())
            and run.get("stat_delta", {})
            .get("statements", {})
            .get("query_text_exported")
            is False,
            "EVIDENCE_STATS_RESET_OR_TEXT",
            f"{run.get('run_id')} statistics reset or query text boundary failed",
            errors,
        )
        require(
            run.get("client_system", {}).get("sample_count", 0) >= 20
            and run.get("server_system", {}).get("sample_count", 0) >= 20
            and run.get("database_waits", {}).get("sample_count", 0) >= 10,
            "EVIDENCE_SAMPLER_INCOMPLETE",
            f"{run.get('run_id')} system or wait samples are incomplete",
            errors,
        )
    require(
        expected_counter
        == Counter(
            {
                ("S", 1): 5,
                ("S", 8): 5,
                ("M", 1): 5,
                ("M", 8): 5,
                ("L", 1): 5,
                ("L", 8): 5,
            }
        ),
        "EVIDENCE_REPETITION_INCOMPLETE",
        "one or more cells do not contain five repetitions",
        errors,
    )
    cells = experiment.get("cell_summaries", [])
    require(
        len(cells) == 6
        and all(cell.get("repetitions") == 5 for cell in cells)
        and all(cell.get("failures") == 0 for cell in cells),
        "EVIDENCE_CELL_SUMMARY_INVALID",
        "cell summaries are incomplete or contain failures",
        errors,
    )
    for cell in cells:
        latency = cell.get("latency_ms", {})
        interval = cell.get("tps", {})
        require(
            latency.get("pooled_sample_count") == cell.get("transactions")
            and 0
            <= latency.get("pooled_p50", -1)
            <= latency.get("pooled_p95", -1)
            <= latency.get("pooled_p99", -1)
            <= latency.get("pooled_max", -1)
            and interval.get("run_count") == 5
            and interval.get("low_95", math.inf)
            <= interval.get("estimate", -math.inf)
            <= interval.get("high_95", -math.inf),
            "EVIDENCE_CELL_DISTRIBUTION_INVALID",
            f"{cell.get('cell_id')} pooled latency or TPS interval is invalid",
            errors,
        )
    pigsty = capacity.get("pigsty_corroboration", {})
    query_results = [
        item.get("result", {}).get("status")
        for item in pigsty.get("queries", {}).values()
    ]
    require(
        pigsty.get("raw_payload_exported") is False
        and query_results
        and all(status in {"observed", "missing", "query-failed"} for status in query_results)
        and "observed" in query_results,
        "EVIDENCE_PIGSTY_INVALID",
        "Pigsty evidence is neither observed nor an explicit gap",
        errors,
    )
    capacity_model = capacity.get("capacity", {})
    require(
        capacity_model.get("production_sustainable_tps") is None
        and capacity_model.get("production_gate") == "pending"
        and all(
            row.get("exact_knee_known") is False
            for row in capacity_model.get("saturation_brackets", [])
        ),
        "EVIDENCE_PRODUCTION_CLAIM",
        "capacity evidence makes an exact-knee or production capacity claim",
        errors,
    )
    require(
        capacity.get("secrets_exported") is False
        and capacity.get("query_text_exported") is False
        and capacity.get("statistics_reset_performed") is False
        and capacity.get("cache_drop_performed") is False
        and capacity.get("configuration_changed") is False,
        "EVIDENCE_BOUNDARY_FAILED",
        "evidence safety or privacy boundary failed",
        errors,
    )
    cleanup = capacity.get("cleanup", {})
    require(
        cleanup.get("database_absent") is True
        and cleanup.get("role_absent") is True
        and cleanup.get("terminated_sessions") == 0,
        "EVIDENCE_CLEANUP_FAILED",
        "database or role cleanup was not proven",
        errors,
    )
    return errors


def build_public_summary(
    preflight: dict[str, Any],
    capacity: dict[str, Any],
    negative_report: dict[str, Any],
) -> dict[str, Any]:
    environment = capacity["environment"]
    initialized = capacity["experiment"]["initialized"]
    cells = []
    for cell in capacity["experiment"]["cell_summaries"]:
        cells.append(
            {
                "cell_id": cell["cell_id"],
                "dataset": {
                    "scale_id": cell["scale_id"],
                    "scale_factor": cell["scale_factor"],
                },
                "clients": cell["clients"],
                "repetitions": cell["repetitions"],
                "transactions": cell["transactions"],
                "failures": cell["failures"],
                "late_transactions": cell["late_transactions"],
                "tps_median": cell["tps"]["estimate"],
                "tps_bootstrap_95": [
                    cell["tps"]["low_95"],
                    cell["tps"]["high_95"],
                ],
                "latency_ms": {
                    "p50": cell["latency_ms"]["pooled_p50"],
                    "p95": cell["latency_ms"]["pooled_p95"],
                    "p99": cell["latency_ms"]["pooled_p99"],
                    "max": cell["latency_ms"]["pooled_max"],
                },
                "server_work_ratio_median": cell["server_cpu"][
                    "work_ratio_median"
                ],
                "server_iowait_ratio_median": cell["server_cpu"][
                    "iowait_ratio_median"
                ],
                "client_work_ratio_median": cell["client_cpu"][
                    "work_ratio_median"
                ],
                "wal_bytes_per_transaction": cell["wal"][
                    "bytes_per_transaction"
                ],
                "wal_records": cell["wal"]["records"],
                "wal_full_page_images": cell["wal"]["full_page_images"],
                "durable_bytes_per_place_order": cell["durable_growth"][
                    "bytes_per_place_order"
                ],
                "block_reads": cell["database"]["block_reads"],
                "block_hits": cell["database"]["block_hits"],
                "temp_bytes": cell["database"]["temp_bytes"],
                "deadlocks": cell["database"]["deadlocks"],
                "wait_types": cell["wait_types"],
            }
        )
    pigsty = {
        name: item["result"]
        for name, item in capacity["pigsty_corroboration"]["queries"].items()
    }
    return {
        "schema": "pg36-ch26-reference-run-v1",
        "release": capacity["release"],
        "captured_at": capacity["captured_at"],
        "run_id": capacity["run_id"],
        "preflight_run_id": preflight["run_id"],
        "target": "pg36-l2-vagrant/pg-test",
        "mode": "bounded-closed-loop-direct-primary-capacity-probe",
        "risk": "L2-bounded-performance-exercise",
        "environment": {
            "client": {
                "host": environment["client"]["hostname"],
                "cpu_count": environment["client"]["resources"]["cpu_count"],
                "memory_bytes": environment["client"]["resources"][
                    "memory_bytes"
                ]["MemTotal"],
                "pgbench": environment["client"]["pgbench_version"],
            },
            "server": {
                "host": environment["server"]["hostname"],
                "cpu_count": environment["server"]["resources"]["cpu_count"],
                "memory_bytes": environment["server"]["resources"][
                    "memory_bytes"
                ]["MemTotal"],
                "postgresql": environment["server"]["postgresql"][
                    "server_version"
                ],
                "shared_buffers_blocks": int(
                    environment["server"]["postgresql"]["settings"][
                        "shared_buffers"
                    ]
                ),
                "shared_buffers_bytes": int(
                    environment["server"]["postgresql"]["settings"][
                        "shared_buffers"
                    ]
                )
                * int(
                    environment["server"]["postgresql"]["settings"][
                        "block_size"
                    ]
                ),
            },
            "client_and_server_are_distinct_hosts": True,
            "connection_path": "direct primary PostgreSQL 5432",
            "haproxy_measured": False,
            "pgbouncer_measured": False,
        },
        "experiment": {
            "workload_id": capacity["experiment"]["workload_id"],
            "arrival_model": "closed-loop",
            "transaction_mix": "read-product 50 / read-order 30 / place-order 20",
            "dataset_scales": initialized,
            "cells": 6,
            "repetitions_per_cell": 5,
            "measured_runs": 30,
            "measured_seconds_per_run": 8,
            "warm_cache_only": True,
            "statistics_reset": False,
            "cells_result": cells,
        },
        "pigsty_corroboration": pigsty,
        "pigsty_window_scope": (
            "the full exercise window, including initialization, warm-up, "
            "measured runs, and gaps between runs; native per-run evidence "
            "is authoritative for cell arithmetic"
        ),
        "capacity_model": capacity["capacity"],
        "validation": {
            "positive_validation_passed": True,
            "counterexamples_rejected": negative_report["rejected"],
            "raw_transaction_logs_public": False,
            "raw_system_samples_public": False,
            "raw_sql_snapshots_public": False,
            "query_text_public": False,
            "secret_material_public": False,
            "database_cleanup_verified": True,
            "role_cleanup_verified": True,
            "remote_temp_cleanup_verified": True,
        },
        "claims_not_made": [
            "the result is universal PostgreSQL performance",
            "the result is production sizing or an admitted-load SLO",
            "the exact saturation knee is known",
            "cold-cache behavior was measured",
            "application, HAProxy, PgBouncer, WAN, backup, maintenance, failure, or recovery capacity was measured",
            "virtual storage represents production IOPS, latency, endurance, or failure domains"
        ],
        "sandbox_ch26_gate": "passed",
        "production_ch26_gate": "pending",
        "production_approval": False,
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    requirements = read_json(source_dir / "requirements.json")
    workload = read_json(source_dir / "workload-contract.json")
    matrix = read_json(source_dir / "experiment-matrix.json")
    model = read_json(source_dir / "capacity-model.json")
    documents = {
        "requirements": requirements,
        "workload": workload,
        "matrix": matrix,
        "model": model,
    }
    errors = validate_contracts(requirements, workload, matrix, model)
    if errors:
        raise ValidationFailure(f"contract validation failed: {errors}")
    expected_hashes = source_hashes(source_dir)
    negative_report = None
    if args.negative_cases:
        negative_report = validate_negative(
            documents,
            read_json(args.negative_cases),
        )
        if args.negative_output:
            args.negative_output.write_text(
                json.dumps(negative_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            args.negative_output.chmod(0o600)
    preflight = None
    capacity = None
    if args.preflight:
        preflight = read_json(args.preflight)
        errors.extend(validate_preflight(preflight, expected_hashes))
    if args.capacity:
        capacity = read_json(args.capacity)
        errors.extend(
            validate_capacity(
                capacity,
                expected_hashes,
                workload,
                matrix,
            )
        )
    if args.cleanup:
        cleanup = read_json(args.cleanup)
        require(
            cleanup.get("schema") == "pg36-ch26-remote-cleanup-v1"
            and cleanup.get("remote_temp_absent") is True
            and cleanup.get("benchmark_return_code") == 0,
            "REMOTE_CLEANUP_FAILED",
            "remote temporary directory cleanup failed",
            errors,
        )
    if errors:
        raise ValidationFailure(f"evidence validation failed: {errors}")
    report = {
        "schema": "pg36-ch26-validation-report-v1",
        "status": "passed",
        "source_files": len(expected_hashes),
        "contracts": 4,
        "preflight_validated": preflight is not None,
        "capacity_evidence_validated": capacity is not None,
        "remote_cleanup_validated": args.cleanup is not None,
        "matrix_cells": 6,
        "measured_runs": 30 if capacity else 0,
        "negative_cases_rejected": (
            negative_report["rejected"] if negative_report else 0
        ),
        "production_ch26_gate": "pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    if args.public_summary:
        if preflight is None or capacity is None or negative_report is None:
            raise ValidationFailure(
                "public summary requires preflight, capacity, and negative report"
            )
        public = build_public_summary(preflight, capacity, negative_report)
        args.public_summary.write_text(
            json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.public_summary.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "verify-ok",
                "cells": report["matrix_cells"],
                "runs": report["measured_runs"],
                "counterexamples": report["negative_cases_rejected"],
                "production_ch26_gate": "pending",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationFailure, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"chapter 26 validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
