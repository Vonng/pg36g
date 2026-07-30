#!/usr/bin/env python3
"""Validate chapter 27 tuning contracts, evidence, and adversarial cases."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from capture import SOURCE_NAMES


class ValidationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--tuning", type=Path)
    parser.add_argument("--cleanup", type=Path)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValidationError("cannot calculate quantile from no values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return (
        ordered[lower] * (upper - position)
        + ordered[upper] * (position - lower)
    )


def bootstrap_interval(values: list[float]) -> list[float]:
    rng = random.Random(270027)
    estimates: list[float] = []
    for _ in range(10000):
        estimates.append(
            statistics.median([rng.choice(values) for _ in values])
        )
    return [quantile(estimates, 0.025), quantile(estimates, 0.975)]


def close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_static(
    source_dir: Path,
    upstream_root: Path,
) -> dict[str, Any]:
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    require(not missing, f"missing source files: {missing}")
    requirements = read_json(source_dir / "requirements.json")
    candidates = read_json(source_dir / "parameter-candidates.json")
    contract = read_json(source_dir / "change-contract.json")
    negative = read_json(source_dir / "negative-cases.json")
    ch26 = read_json(upstream_root / "ch26" / "capacity-run.json")
    require(
        requirements["schema"] == "pg36-ch27-requirements-v1",
        "requirements schema mismatch",
    )
    require(
        requirements["target"]["production_data_permitted"] is False
        and requirements["target"]["production_traffic_permitted"] is False,
        "production mutation must be forbidden",
    )
    require(
        ch26["run_id"] == requirements["upstream"]["required_run_id"],
        "chapter 26 upstream run mismatch",
    )
    require(
        ch26["capacity_model"]["production_sustainable_tps"] is None,
        "chapter 26 production TPS must remain null",
    )
    require(
        all(
            row["exact_knee_known"] is False
            for row in ch26["capacity_model"]["saturation_brackets"]
        ),
        "chapter 26 exact knee must remain unknown",
    )
    require(
        all(row["temp_bytes"] == 0 for row in ch26["experiment"]["results"]),
        "chapter 26 temp-byte premise changed",
    )
    tested = [row for row in candidates["candidates"] if row.get("tested") is True]
    require(
        len(tested) == 1 and tested[0]["parameter"] == "plan_cache_mode",
        "exactly one parameter must be tested",
    )
    require(
        contract["parameter"]
        == {
            "name": "plan_cache_mode",
            "baseline": "auto",
            "candidate": "force_generic_plan",
            "context_required": "user",
            "applied_with": "PGOPTIONS=-c plan_cache_mode=<arm>",
            "scope": "benchmark session",
            "persistent": False,
            "rollback": "end the session; RESET plan_cache_mode if reused",
        },
        "parameter contract mismatch",
    )
    require(
        contract["acceptance"]["paired_tps_ratio_bootstrap_95_lower_min"]
        == 1.02
        and contract["acceptance"]["candidate_p95_ratio_max"] == 1.05,
        "acceptance thresholds changed",
    )
    require(
        len(negative["cases"]) == 28
        and len({row["id"] for row in negative["cases"]}) == 28,
        "negative-case catalog mismatch",
    )
    executable_text = "\n".join(
        (source_dir / name).read_text(encoding="utf-8")
        for name in (
            "remote_experiment.py",
            "capture.py",
            "validate.py",
            "review.py",
            "task.sh",
        )
    )
    forbidden = (
        "ALTER" + " SYSTEM",
        "patronictl" + " edit-config",
        "pg_stat_" + "reset(",
        "/proc/sys/vm/" + "drop_caches",
        "DROP DATABASE " + "pg36_tuning WITH (FORCE)",
    )
    require(
        not any(token in executable_text for token in forbidden),
        "executable source contains a forbidden configuration or reset action",
    )
    require(
        "PGOPTIONS" in executable_text
        and "plan_cache_mode={mode}" in executable_text,
        "session-local parameter application is missing",
    )
    return {
        "requirements": requirements,
        "candidates": candidates,
        "contract": contract,
        "negative": negative,
        "ch26": ch26,
        "ch26_sha256": sha256(upstream_root / "ch26" / "capacity-run.json"),
        "source_hashes": {
            name: sha256(source_dir / name)
            for name in SOURCE_NAMES
        },
    }


def canonical_decision_model() -> dict[str, Any]:
    return {
        "target": "pg36-l2-vagrant/pg-test",
        "primary": True,
        "clean_start": True,
        "upstream_run": "required",
        "exact_knee_known": False,
        "production_tps": None,
        "tested_parameters": ["plan_cache_mode"],
        "method": "PGOPTIONS-session",
        "persistent": False,
        "restart": False,
        "durability": {
            "synchronous_commit": "on",
            "fsync": "on",
            "full_page_writes": "on",
        },
        "statistics_reset": False,
        "cache_drop": False,
        "paired_seeds": True,
        "counterbalanced": True,
        "raw_logs_complete": True,
        "quantile_method": "pooled-raw-samples",
        "failures_reported": True,
        "plan_shapes_equal": True,
        "global_settings_unchanged": True,
        "bootstrap_lower": 1.03,
        "p95_ratio": 1.00,
        "decision": "candidate-worthy-for-larger-canary",
        "marker_match": True,
        "drop_with_force": False,
        "public_has_secret": False,
        "public_has_query": False,
        "production_gate": "pending",
    }


def validate_decision_model(model: dict[str, Any]) -> None:
    require(model["target"] == "pg36-l2-vagrant/pg-test", "wrong target")
    require(model["primary"] is True, "target is not primary")
    require(model["clean_start"] is True, "fixture does not start clean")
    require(model["upstream_run"] == "required", "upstream run mismatch")
    require(model["exact_knee_known"] is False, "exact knee was fabricated")
    require(model["production_tps"] is None, "production TPS was fabricated")
    require(
        model["tested_parameters"] == ["plan_cache_mode"],
        "more than one parameter changed",
    )
    require(model["method"] == "PGOPTIONS-session", "persistent method used")
    require(model["persistent"] is False, "persistent change used")
    require(model["restart"] is False, "restart used")
    require(
        model["durability"]
        == {
            "synchronous_commit": "on",
            "fsync": "on",
            "full_page_writes": "on",
        },
        "durability changed",
    )
    require(model["statistics_reset"] is False, "statistics reset used")
    require(model["cache_drop"] is False, "cache drop used")
    require(model["paired_seeds"] is True, "seeds are not paired")
    require(model["counterbalanced"] is True, "run order is not counterbalanced")
    require(model["raw_logs_complete"] is True, "raw log missing")
    require(
        model["quantile_method"] == "pooled-raw-samples",
        "quantile was not recomputed",
    )
    require(model["failures_reported"] is True, "failure was hidden")
    require(model["plan_shapes_equal"] is True, "plan change was hidden")
    require(
        model["global_settings_unchanged"] is True,
        "global setting drift was hidden",
    )
    material = model["bootstrap_lower"] >= 1.02
    tail_ok = model["p95_ratio"] <= 1.05
    expected = (
        "candidate-worthy-for-larger-canary"
        if material and tail_ok
        else "reject-persistent-change"
    )
    require(model["decision"] == expected, "decision contradicts thresholds")
    require(model["marker_match"] is True, "cleanup marker mismatch")
    require(model["drop_with_force"] is False, "forced drop used")
    require(model["public_has_secret"] is False, "secret leaked")
    require(model["public_has_query"] is False, "query text leaked")
    require(model["production_gate"] == "pending", "production gate advanced")


def apply_mutation(model: dict[str, Any], case_id: str) -> None:
    if case_id == "wrong-target":
        model["target"] = "production"
    elif case_id == "recovery-target":
        model["primary"] = False
    elif case_id in {"existing-database", "existing-role"}:
        model["clean_start"] = False
    elif case_id == "missing-upstream-run":
        model["upstream_run"] = "unknown"
    elif case_id == "fabricated-knee":
        model["exact_knee_known"] = True
    elif case_id == "fabricated-production-tps":
        model["production_tps"] = 2900
    elif case_id == "two-parameters":
        model["tested_parameters"].append("work_mem")
    elif case_id in {"persistent-alter-system", "patroni-edit"}:
        model["method"] = case_id
        model["persistent"] = True
    elif case_id == "restart":
        model["restart"] = True
    elif case_id == "durability-change":
        model["durability"]["synchronous_commit"] = "off"
    elif case_id == "statistics-reset":
        model["statistics_reset"] = True
    elif case_id == "cache-drop":
        model["cache_drop"] = True
    elif case_id == "unpaired-seeds":
        model["paired_seeds"] = False
    elif case_id == "fixed-run-order":
        model["counterbalanced"] = False
    elif case_id == "missing-raw-log":
        model["raw_logs_complete"] = False
    elif case_id == "averaged-p95":
        model["quantile_method"] = "average-run-p95"
    elif case_id == "failure-hidden":
        model["failures_reported"] = False
    elif case_id == "plan-change-hidden":
        model["plan_shapes_equal"] = False
    elif case_id == "global-drift-hidden":
        model["global_settings_unchanged"] = False
    elif case_id == "weak-benefit-accepted":
        model["bootstrap_lower"] = 1.00
    elif case_id == "tail-regression-accepted":
        model["p95_ratio"] = 1.10
    elif case_id == "marker-mismatch-cleanup":
        model["marker_match"] = False
    elif case_id == "force-drop":
        model["drop_with_force"] = True
    elif case_id == "secret-public":
        model["public_has_secret"] = True
    elif case_id == "raw-query-public":
        model["public_has_query"] = True
    elif case_id == "production-approved":
        model["production_gate"] = "accepted"
    else:
        raise ValidationError(f"unknown negative case: {case_id}")


def run_negative_cases(catalog: dict[str, Any]) -> dict[str, Any]:
    validate_decision_model(canonical_decision_model())
    results = []
    for case in catalog["cases"]:
        model = copy.deepcopy(canonical_decision_model())
        apply_mutation(model, case["id"])
        rejected = False
        message = ""
        try:
            validate_decision_model(model)
        except ValidationError as exc:
            rejected = True
            message = str(exc)
        require(rejected, f"negative case was accepted: {case['id']}")
        results.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "observed": "rejected",
                "reason": message,
            }
        )
    return {
        "schema": "pg36-ch27-negative-report-v1",
        "positive_model_passed": True,
        "counterexamples": len(results),
        "all_rejected": True,
        "results": results,
    }


def parse_transaction_logs(run_dir: Path) -> dict[str, Any]:
    paths = sorted(run_dir.glob("transactions.*"))
    require(paths, f"missing transaction log in {run_dir}")
    latencies: list[float] = []
    failures = 0
    skipped = 0
    script_counts = {0: 0, 1: 0, 2: 0}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            require(len(fields) >= 6, f"malformed transaction row in {path}")
            latency = fields[2]
            if latency == "skipped":
                skipped += 1
            elif latency in {"failed", "serialization", "deadlock"}:
                failures += 1
            else:
                latencies.append(int(latency) / 1000.0)
                script_id = int(fields[3])
                require(script_id in script_counts, "unknown transaction script")
                script_counts[script_id] += 1
    return {
        "files": [path.name for path in paths],
        "transactions": len(latencies),
        "failures": failures,
        "skipped": skipped,
        "latencies": latencies,
        "latency_ms": {
            "p50": quantile(latencies, 0.50),
            "p95": quantile(latencies, 0.95),
            "p99": quantile(latencies, 0.99),
            "max": max(latencies),
        },
        "script_counts": script_counts,
    }


def validate_full(
    static: dict[str, Any],
    preflight_path: Path,
    tuning_path: Path,
    cleanup_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    preflight = read_json(preflight_path)
    tuning = read_json(tuning_path)
    cleanup = read_json(cleanup_path)
    require(
        preflight["schema"] == "pg36-ch27-preflight-evidence-v1"
        and preflight["mutation"] == "none"
        and preflight["target"] == "pg36-l2-vagrant/pg-test",
        "preflight identity mismatch",
    )
    require(
        preflight["clean_start"]
        == {"database_absent": True, "role_absent": True},
        "preflight clean start failed",
    )
    require(
        preflight["source_hashes"] == static["source_hashes"],
        "source changed after preflight",
    )
    require(
        preflight["upstream"]["chapter26_sha256"] == static["ch26_sha256"],
        "chapter 26 input changed after preflight",
    )
    require(
        tuning["schema"] == "pg36-ch27-tuning-evidence-v1"
        and tuning["status"] == "passed"
        and tuning["target"] == "pg36-l2-vagrant/pg-test",
        "tuning evidence identity mismatch",
    )
    require(
        tuning["parameter"]
        == {
            "name": "plan_cache_mode",
            "baseline": "auto",
            "candidate": "force_generic_plan",
            "scope": "benchmark-session-only",
            "persistent_configuration_change": False,
        },
        "tuning parameter scope mismatch",
    )
    require(
        tuning["global_settings_unchanged"] is True
        and tuning["settings_before"]["settings"]
        == tuning["settings_after"]["settings"]
        and tuning["settings_before"]["file_errors"] == []
        and tuning["settings_after"]["file_errors"] == [],
        "global settings drifted or file errors appeared",
    )
    settings = {
        row["name"]: row
        for row in tuning["settings_before"]["settings"]
    }
    require(
        settings["plan_cache_mode"]["setting"] == "auto"
        and settings["plan_cache_mode"]["context"] == "user"
        and settings["synchronous_commit"]["setting"] == "on"
        and settings["fsync"]["setting"] == "on"
        and settings["full_page_writes"]["setting"] == "on",
        "parameter or durability setting mismatch",
    )
    runs = tuning["runs"]
    require(len(runs) == 10, "expected ten measured runs")
    require(
        {row["mode"] for row in runs} == {"auto", "force_generic_plan"},
        "experiment arm mismatch",
    )
    require(
        all(
            sum(
                row["mode"] == mode and row["repetition"] == repetition
                for row in runs
            )
            == 1
            for mode in ("auto", "force_generic_plan")
            for repetition in range(1, 6)
        ),
        "paired repetition matrix is incomplete",
    )
    for repetition in range(1, 6):
        pair = [row for row in runs if row["repetition"] == repetition]
        require(len({row["seed"] for row in pair}) == 1, "paired seed mismatch")
        expected_order = (
            ["auto", "force_generic_plan"]
            if repetition % 2 == 1
            else ["force_generic_plan", "auto"]
        )
        observed_order = [
            row["mode"] for row in sorted(pair, key=lambda item: item["sequence"])
        ]
        require(observed_order == expected_order, "run order is not counterbalanced")
    remote_root = tuning_path.parent
    arm_latencies: dict[str, list[float]] = {
        "auto": [],
        "force_generic_plan": [],
    }
    raw_files = 0
    for row in runs:
        run_dir = remote_root / "runs" / row["run_id"]
        require(run_dir.is_dir(), f"missing run directory {run_dir}")
        raw = parse_transaction_logs(run_dir)
        raw_files += len(list(run_dir.iterdir()))
        require(
            raw["transactions"] == row["pgbench"]["processed_transactions"]
            == row["transactions"]["transactions"],
            f"transaction count mismatch in {row['run_id']}",
        )
        require(
            raw["failures"] == row["transactions"]["failures"] == 0
            and raw["skipped"] == row["transactions"]["skipped"] == 0
            and row["pgbench"]["failed_transactions"] == 0
            and row["pgbench"]["late_transactions"] == 0,
            f"failure, late, or skipped transaction in {row['run_id']}",
        )
        for key in ("p50", "p95", "p99", "max"):
            require(
                close(raw["latency_ms"][key], row["transactions"]["latency_ms"][key]),
                f"latency mismatch in {row['run_id']} {key}",
            )
        require(
            row["database_delta"]["temp_bytes"] == 0
            and row["database_delta"]["deadlocks"] == 0,
            f"temp or deadlock regression in {row['run_id']}",
        )
        arm_latencies[row["mode"]].extend(raw["latencies"])
    recomputed_arms: dict[str, Any] = {}
    for mode in ("auto", "force_generic_plan"):
        rows = [row for row in runs if row["mode"] == mode]
        values = arm_latencies[mode]
        recomputed_arms[mode] = {
            "runs": len(rows),
            "transactions": sum(
                row["pgbench"]["processed_transactions"] for row in rows
            ),
            "failures": 0,
            "late_transactions": 0,
            "skipped_transactions": 0,
            "tps_median": statistics.median(
                row["pgbench"]["tps"] for row in rows
            ),
            "latency_ms": {
                "p50": quantile(values, 0.50),
                "p95": quantile(values, 0.95),
                "p99": quantile(values, 0.99),
                "max": max(values),
            },
            "temp_bytes": 0,
            "deadlocks": 0,
        }
    summary = tuning["summary"]
    for mode in recomputed_arms:
        require(
            recomputed_arms[mode] == summary["arms"][mode],
            f"arm summary mismatch for {mode}",
        )
    ratios = []
    for repetition in range(1, 6):
        baseline = next(
            row for row in runs
            if row["mode"] == "auto" and row["repetition"] == repetition
        )
        candidate = next(
            row for row in runs
            if row["mode"] == "force_generic_plan"
            and row["repetition"] == repetition
        )
        ratios.append(
            candidate["pgbench"]["tps"] / baseline["pgbench"]["tps"]
        )
    ratio_ci = bootstrap_interval(ratios)
    p95_ratio = (
        recomputed_arms["force_generic_plan"]["latency_ms"]["p95"]
        / recomputed_arms["auto"]["latency_ms"]["p95"]
    )
    require(
        all(
            close(left, right)
            for left, right in zip(ratios, summary["paired_tps_ratios"])
        )
        and all(
            close(left, right)
            for left, right in zip(
                ratio_ci, summary["paired_tps_ratio_bootstrap_95"]
            )
        )
        and close(p95_ratio, summary["candidate_p95_ratio"]),
        "paired effect summary mismatch",
    )
    probes = tuning["plan_probes"]
    require(set(probes) == {"auto", "force_generic_plan"}, "plan probes missing")
    fingerprints = {}
    for mode, probe in probes.items():
        require(
            probe["prepared_counts"]["effective_mode"] == mode,
            f"plan probe mode mismatch for {mode}",
        )
        fingerprints[mode] = {
            (row["script"], row["probe_value"]): row["shape_sha256"]
            for row in probe["probes"]
        }
        for row in probe["probes"]:
            encoded = json.dumps(
                row["shape"], sort_keys=True, separators=(",", ":")
            ).encode()
            require(
                hashlib.sha256(encoded).hexdigest() == row["shape_sha256"],
                "plan shape fingerprint mismatch",
            )
    shapes_equal = fingerprints["auto"] == fingerprints["force_generic_plan"]
    require(
        shapes_equal == summary["plan_shapes_equal_for_probes"],
        "plan equality claim mismatch",
    )
    rules = {
        "all_runs_successful": True,
        "plan_shapes_equal_for_probes": shapes_equal,
        "global_settings_unchanged": True,
        "candidate_p95_ratio_at_most_1_05": p95_ratio <= 1.05,
        "paired_tps_ratio_bootstrap_lower_at_least_1_02": ratio_ci[0] >= 1.02,
    }
    expected_decision = (
        "candidate-worthy-for-larger-canary"
        if all(rules.values())
        else "reject-persistent-change"
    )
    require(
        summary["acceptance_rules"] == rules
        and summary["decision"] == expected_decision
        and summary["production_ch27_gate"] == "pending",
        "decision does not follow predeclared rules",
    )
    require(
        tuning["cleanup"]
        == {
            "database_absent": True,
            "role_absent": True,
            "marker_matched": True,
            "unrelated_sessions_terminated": 0,
            "drop_with_force_used": False,
        },
        "fixture cleanup evidence mismatch",
    )
    require(
        cleanup["schema"] == "pg36-ch27-remote-cleanup-v1"
        and cleanup["remote_temp_absent"] is True
        and cleanup["experiment_return_code"] == 0,
        "remote cleanup evidence mismatch",
    )
    public = {
        "schema": "pg36-ch27-reference-run-v1",
        "release": "1.0-sandbox",
        "captured_at": tuning["captured_at"],
        "run_id": tuning["run_id"],
        "preflight_run_id": preflight["preflight_run_id"],
        "target": tuning["target"],
        "risk": tuning["risk"],
        "upstream": {
            "chapter26_run_id": preflight["upstream"]["chapter26_run_id"],
            "chapter26_exact_knee_known": False,
            "chapter26_production_tps": None,
            "chapter26_all_temp_bytes_zero": True,
        },
        "environment": {
            "client": {
                "host": preflight["remote"]["client"]["hostname"],
                "cpu_count": preflight["remote"]["client"]["cpu_count"],
            },
            "server": {
                "host": preflight["remote"]["server"]["hostname"],
                "cpu_count": preflight["remote"]["server"]["cpu_count"],
                "memory_bytes": preflight["remote"]["server"]["memory_bytes"]["MemTotal"],
                "postgresql": preflight["remote"]["postgresql"]["server_version"],
            },
            "configuration_facts": {
                name: {
                    "setting": row["setting"],
                    "unit": row["unit"],
                    "context": row["context"],
                    "source": row["source"],
                    "pending_restart": row["pending_restart"],
                }
                for name, row in settings.items()
                if name
                in {
                    "plan_cache_mode",
                    "work_mem",
                    "shared_buffers",
                    "effective_cache_size",
                    "max_connections",
                    "synchronous_commit",
                    "fsync",
                    "full_page_writes",
                    "wal_compression",
                }
            },
        },
        "hypothesis": {
            "parameter": "plan_cache_mode",
            "baseline": "auto",
            "candidate": "force_generic_plan",
            "scope": "benchmark-session-only",
            "persistent_configuration_change": False,
            "rollback": "session-end",
        },
        "experiment": {
            "dataset_scale": "M",
            "clients": 8,
            "measured_seconds_per_run": 12,
            "paired_repetitions": 5,
            "measured_runs": 10,
            "transactions": sum(
                arm["transactions"] for arm in recomputed_arms.values()
            ),
            "counterbalanced": True,
            "paired_seeds": True,
            "arms": recomputed_arms,
            "paired_tps_ratio_median": summary["paired_tps_ratio_median"],
            "paired_tps_ratio_bootstrap_95": ratio_ci,
            "candidate_p95_ratio": p95_ratio,
            "plan_shapes_equal_for_probes": shapes_equal,
            "prepared_plan_counts": {
                mode: probe["prepared_counts"]["prepared"]
                for mode, probe in probes.items()
            },
        },
        "decision": {
            "result": expected_decision,
            "rules": rules,
            "minimum_material_gain_percent": 2,
            "candidate_p95_ratio_max": 1.05,
            "persistent_change_applied": False,
            "production_ch27_gate": "pending",
        },
        "rejected_untested_changes": [
            {
                "parameter": row["parameter"],
                "reason": row["rejection"],
            }
            for row in static["candidates"]["candidates"]
            if row.get("tested") is False
        ],
        "validation": {
            "positive_validation_passed": True,
            "counterexamples_rejected": 28,
            "raw_transaction_logs_public": False,
            "raw_settings_paths_public": False,
            "raw_query_text_public": False,
            "secret_material_public": False,
            "global_settings_unchanged": True,
            "database_cleanup_verified": True,
            "role_cleanup_verified": True,
            "remote_temp_cleanup_verified": True,
            "raw_files_verified": raw_files,
        },
    }
    report = {
        "schema": "pg36-ch27-validation-report-v1",
        "status": "passed",
        "mode": "full",
        "run_id": tuning["run_id"],
        "measured_runs": 10,
        "raw_files_verified": raw_files,
        "decision": expected_decision,
        "production_ch27_gate": "pending",
    }
    return report, public


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    static = validate_static(source_dir, upstream_root)
    negative = run_negative_cases(static["negative"])
    write_json(args.negative_output.resolve(), negative)
    full_args = (args.preflight, args.tuning, args.cleanup)
    if all(value is None for value in full_args):
        report = {
            "schema": "pg36-ch27-validation-report-v1",
            "status": "passed",
            "mode": "lint",
            "source_files": len(SOURCE_NAMES),
            "counterexamples_rejected": 28,
            "planned_runs": 10,
            "production_ch27_gate": "pending",
        }
        write_json(args.output.resolve(), report)
        print(
            json.dumps(
                {
                    "status": "verify-ok",
                    "mode": "lint",
                    "counterexamples": 28,
                    "production_ch27_gate": "pending",
                },
                separators=(",", ":"),
            )
        )
        return 0
    require(all(value is not None for value in full_args), "full evidence is incomplete")
    report, public = validate_full(
        static,
        args.preflight.resolve(),
        args.tuning.resolve(),
        args.cleanup.resolve(),
    )
    write_json(args.output.resolve(), report)
    if args.public_summary is not None:
        write_json(args.public_summary.resolve(), public)
    print(
        json.dumps(
            {
                "status": "verify-ok",
                "mode": "full",
                "runs": report["measured_runs"],
                "counterexamples": 28,
                "decision": report["decision"],
                "production_ch27_gate": "pending",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"chapter 27 validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
