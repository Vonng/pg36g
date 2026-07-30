#!/usr/bin/env python3
"""Run the guarded chapter 35 clone-only forensic exercise."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

from common import (
    LabError,
    read_json,
    run,
    sha256_file,
    ssh_base,
    utc_now,
    write_json,
)


SOURCE_FILES = (
    "requirements.json",
    "classification-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "l3-rebuild-plan.json",
    "common.py",
    "capture.py",
    "exercise.py",
    "classify.py",
    "validate.py",
    "review.py",
    "task.sh",
)


REMOTE_PROGRAM = r'''
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


CONFIG = json.loads(__CONFIG_JSON__)


class ExerciseError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(args, timeout=60, check=True):
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExerciseError("cannot execute " + str(args[0]) + ": " + str(exc))
    if check and result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        detail = lines[-1] if lines else "exit " + str(result.returncode)
        raise ExerciseError("command failed (" + str(args[0]) + "): " + detail)
    return result


def json_value(raw, label):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExerciseError(label + " returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExerciseError(label + " returned no object")
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_digest(root):
    digest = hashlib.sha256()
    files = 0
    total = 0
    for path in sorted(root.rglob("*"), key=lambda value: str(value)):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root)).encode()
        payload_hash = sha256_file(path).encode()
        size = path.stat().st_size
        digest.update(relative + b"\0" + str(size).encode() + b"\0")
        digest.update(payload_hash + b"\n")
        files += 1
        total += size
    return {
        "sha256": digest.hexdigest(),
        "files": files,
        "bytes": total,
    }


run_id = CONFIG["run_id"]
if not re.fullmatch(r"[0-9a-f-]{36}", run_id):
    raise ExerciseError("run identity is unsafe")
root = Path(str(CONFIG["root_prefix"]) + "-" + run_id)
if (
    not re.fullmatch(
        r"/tmp/pg36-ch35-forensics-[0-9a-f-]{36}",
        str(root),
    )
    or root.exists()
):
    raise ExerciseError("forensic root is unsafe or already exists")

marker = root / ".pg36-ch35-owned"
source_data = root / "source"
golden_data = root / "known-good"
socket_dir = root / "socket"
port = int(CONFIG["port"])
active_data = None
result = None


def executable(name):
    bindir = run(["pg_config", "--bindir"]).stdout.strip()
    path = Path(bindir) / name
    if not path.is_file():
        raise ExerciseError("PostgreSQL executable missing: " + str(path))
    return str(path)


initdb = executable("initdb")
pg_ctl = executable("pg_ctl")
psql_bin = executable("psql")
pg_checksums = executable("pg_checksums")


def start(data_dir, label):
    global active_data
    if active_data is not None:
        raise ExerciseError("another disposable postmaster is already active")
    run(
        [
            pg_ctl,
            "-D",
            str(data_dir),
            "-l",
            str(root / (label + ".log")),
            "-w",
            "start",
        ],
        timeout=120,
    )
    active_data = data_dir


def stop():
    global active_data
    if active_data is None:
        return
    value = active_data
    active_data = None
    run(
        [
            pg_ctl,
            "-D",
            str(value),
            "-m",
            "fast",
            "-w",
            "stop",
        ],
        timeout=120,
    )


def psql(sql, timeout=60, check=True, verbose=False):
    args = [
        psql_bin,
        "-X",
        "-qAt",
        "-h",
        str(socket_dir),
        "-p",
        str(port),
        "-U",
        "postgres",
        "-d",
        "postgres",
        "--set=ON_ERROR_STOP=1",
    ]
    if verbose:
        args.append("--set=VERBOSITY=verbose")
    args.extend(["-c", sql])
    return run(args, timeout=timeout, check=check)


def sql_json(sql, label):
    return json_value(psql(sql).stdout.strip(), label)


def amcheck():
    value = psql(
        "SELECT public.bt_index_check("
        "'public.pg36_ch35_code_idx'::regclass, true)"
    )
    return {
        "structural_check_passed": value.returncode == 0,
        "heapallindexed": True,
        "index": "public.pg36_ch35_code_idx",
    }


def business_invariants():
    return sql_json(
        """
        SELECT json_build_object(
            'row_count', count(*)::bigint,
            'sum_id', sum(id)::bigint,
            'sum_balance', sum(balance)::bigint,
            'ordered_content_digest',
                md5(
                    string_agg(
                        md5(
                            id::text || '|' || code || '|' ||
                            balance::text || '|' || payload
                        ),
                        '' ORDER BY id
                    )
                )
        )
        FROM public.pg36_ch35_accounts
        """,
        "business invariant projection",
    )


def relation_projection():
    return sql_json(
        """
        SELECT json_build_object(
            'heap_path',
                pg_relation_filepath('public.pg36_ch35_accounts'),
            'heap_filenode',
                pg_relation_filenode(
                    'public.pg36_ch35_accounts'::regclass
                ),
            'heap_bytes',
                pg_relation_size('public.pg36_ch35_accounts'),
            'heap_blocks',
                pg_relation_size('public.pg36_ch35_accounts') / 8192,
            'index_path',
                pg_relation_filepath('public.pg36_ch35_code_idx'),
            'index_filenode',
                pg_relation_filenode(
                    'public.pg36_ch35_code_idx'::regclass
                ),
            'index_bytes',
                pg_relation_size('public.pg36_ch35_code_idx')
        )
        """,
        "relation projection",
    )


def collation_projection():
    return sql_json(
        """
        SELECT json_build_object(
            'name', n.nspname || '.' || c.collname,
            'provider', c.collprovider,
            'stored_version', c.collversion,
            'actual_version',
                pg_collation_actual_version(c.oid),
            'version_mismatch',
                c.collversion IS DISTINCT FROM
                pg_collation_actual_version(c.oid)
        )
        FROM pg_collation AS c
        JOIN pg_namespace AS n ON n.oid = c.collnamespace
        WHERE n.nspname = 'public'
          AND c.collname = 'pg36_ch35_icu'
        """,
        "collation projection",
    )


def checksum_projection(data_dir):
    value = run(
        [
            pg_checksums,
            "--check",
            "-D",
            str(data_dir),
        ],
        timeout=180,
        check=False,
    )
    combined = value.stdout + "\n" + value.stderr

    def field(label):
        match = re.search(
            re.escape(label) + r"\s*:\s*([0-9]+)",
            combined,
            re.IGNORECASE,
        )
        return int(match.group(1)) if match else None

    bad = field("Bad checksums")
    if bad is None:
        if value.returncode == 0:
            bad = 0
        else:
            raise ExerciseError(
                "pg_checksums failed without a bad-checksum count"
            )
    return {
        "enabled": True,
        "returncode": value.returncode,
        "offline_bad_checksums": bad,
        "files_scanned": field("Files scanned"),
        "blocks_scanned": field("Blocks scanned"),
        "raw_output_exported": False,
    }


def copy_cluster(source, target):
    if target.exists():
        raise ExerciseError("refusing to overwrite clone: " + str(target))
    shutil.copytree(source, target)


def inject_heap_bit(case_dir, relation):
    block = int(CONFIG["physical"]["mutated_block"])
    within = int(CONFIG["physical"]["byte_offset_within_block"])
    offset = block * 8192 + within
    relation_file = case_dir / relation["heap_path"]
    if (
        not relation_file.is_file()
        or relation["heap_blocks"] < int(CONFIG["minimum_heap_blocks"])
        or offset >= relation_file.stat().st_size
    ):
        raise ExerciseError("fixture relation is too small for mutation")
    before_hash = sha256_file(relation_file)
    with relation_file.open("r+b", buffering=0) as stream:
        stream.seek(offset)
        original = stream.read(1)
        if len(original) != 1:
            raise ExerciseError("cannot read target mutation byte")
        changed = bytes([original[0] ^ 0x01])
        stream.seek(offset)
        stream.write(changed)
        os.fsync(stream.fileno())
    after_hash = sha256_file(relation_file)
    if before_hash == after_hash:
        raise ExerciseError("heap mutation did not change relation hash")
    return {
        "method": "xor-one-bit",
        "relation_path": relation["heap_path"],
        "block": block,
        "byte_offset_within_block": within,
        "absolute_byte_offset": offset,
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "bytes_changed": 1,
        "server_running_during_mutation": False,
    }


def online_scan_projection():
    value = psql(
        """
        SET enable_indexscan = off;
        SET enable_indexonlyscan = off;
        SET enable_bitmapscan = off;
        SET max_parallel_workers_per_gather = 0;
        SELECT sum(length(payload))
        FROM public.pg36_ch35_accounts;
        """,
        timeout=60,
        check=False,
        verbose=True,
    )
    match = re.search(
        r"ERROR:\s+([A-Z0-9]{5}):",
        value.stderr,
    )
    return {
        "scan_succeeded": value.returncode == 0,
        "returncode": value.returncode,
        "sqlstate": match.group(1) if match else None,
        "raw_error_exported": False,
        "ignore_checksum_failure": False,
        "zero_damaged_pages": False,
    }


def run_physical(case_id, baseline, relation):
    case_dir = root / ("case-" + case_id)
    recovery_dir = root / ("recovery-" + case_id)
    copy_cluster(golden_data, case_dir)
    mutation = inject_heap_bit(case_dir, relation)
    checksum = checksum_projection(case_dir)
    start(case_dir, "physical-" + case_id)
    scan = online_scan_projection()
    collation = collation_projection()
    stop()
    case_digest_before = tree_digest(case_dir)

    packet = {
        "case_id": case_id,
        "observed_at": utc_now(),
        "checksum": checksum,
        "relation": {
            "kind": "heap",
            "identity": "public.pg36_ch35_accounts",
            "mutated_block": mutation["block"],
        },
        "collation": {
            "version_mismatch": collation["version_mismatch"],
        },
        "amcheck": {
            "structural_check_passed": False,
            "not_run_reason": "heap scan already proved physical damage",
        },
        "business": {
            "baseline_digest": baseline["ordered_content_digest"],
            "online_scan_succeeded": scan["scan_succeeded"],
        },
    }

    copy_cluster(golden_data, recovery_dir)
    start(recovery_dir, "physical-recovery-" + case_id)
    recovered_invariants = business_invariants()
    recovered_amcheck = amcheck()
    recovered_collation = collation_projection()
    stop()
    recovered_checksum = checksum_projection(recovery_dir)
    case_digest_after = tree_digest(case_dir)
    return {
        "case_id": case_id,
        "scenario": "PHYSICAL_HEAP_PAGE",
        "expected_route": "RESTORE_FROM_KNOWN_GOOD_COPY",
        "blind_packet": packet,
        "injection": mutation,
        "observed": {
            "checksum": checksum,
            "online_scan": scan,
            "collation": collation,
        },
        "recovery": {
            "strategy": "new-copy-from-known-good-stopped-snapshot",
            "in_place_repair": False,
            "dangerous_gucs_used": False,
            "manual_pg_wal_file_deletion": False,
            "business_invariants": recovered_invariants,
            "business_invariants_match": recovered_invariants == baseline,
            "amcheck": recovered_amcheck,
            "collation": recovered_collation,
            "checksum": recovered_checksum,
        },
        "evidence_copy": {
            "preserved_until_final_cleanup": (
                case_digest_before == case_digest_after
                and case_dir.exists()
            ),
            "digest_before_recovery": case_digest_before,
            "digest_after_recovery": case_digest_after,
        },
    }


def run_collation(case_id, baseline):
    case_dir = root / ("case-" + case_id)
    working_dir = root / ("working-" + case_id)
    copy_cluster(golden_data, case_dir)
    start(case_dir, "collation-" + case_id)
    before = collation_projection()
    fake_version = (
        str(CONFIG["collation"]["injected_version_prefix"])
        + run_id[:8]
    )
    psql(
        """
        UPDATE pg_catalog.pg_collation
        SET collversion = '%s'
        WHERE oid = 'public.pg36_ch35_icu'::regcollation
        """
        % fake_version
    )
    after_injection = collation_projection()
    before_amcheck = amcheck()
    before_business = business_invariants()
    stop()
    checksum = checksum_projection(case_dir)
    case_digest_before = tree_digest(case_dir)

    packet = {
        "case_id": case_id,
        "observed_at": utc_now(),
        "checksum": checksum,
        "relation": {
            "kind": "index-derived",
            "identity": "public.pg36_ch35_code_idx",
            "source_relation": "public.pg36_ch35_accounts",
        },
        "collation": {
            "name": after_injection["name"],
            "version_mismatch": after_injection["version_mismatch"],
            "stored_version": after_injection["stored_version"],
            "actual_version": after_injection["actual_version"],
        },
        "amcheck": before_amcheck,
        "business": {
            "baseline_digest": baseline["ordered_content_digest"],
            "current_validation_passed": before_business == baseline,
        },
    }

    copy_cluster(case_dir, working_dir)
    start(working_dir, "collation-working-" + case_id)
    steps = []
    started = time.monotonic_ns()
    psql("REINDEX INDEX public.pg36_ch35_code_idx")
    steps.append(
        {
            "sequence": 1,
            "action": "REINDEX INDEX public.pg36_ch35_code_idx",
            "finished_monotonic_ns": time.monotonic_ns(),
        }
    )
    psql(
        "ALTER COLLATION public.pg36_ch35_icu REFRESH VERSION"
    )
    steps.append(
        {
            "sequence": 2,
            "action": (
                "ALTER COLLATION public.pg36_ch35_icu REFRESH VERSION"
            ),
            "finished_monotonic_ns": time.monotonic_ns(),
        }
    )
    repaired_collation = collation_projection()
    repaired_amcheck = amcheck()
    repaired_business = business_invariants()
    stop()
    repaired_checksum = checksum_projection(working_dir)
    case_digest_after = tree_digest(case_dir)
    return {
        "case_id": case_id,
        "scenario": "COLLATION_METADATA",
        "expected_route": "REINDEX_AND_REFRESH_COLLATION",
        "blind_packet": packet,
        "injection": {
            "method": "exact-system-catalog-version-metadata-update",
            "target": "public.pg36_ch35_icu",
            "metadata_only": True,
            "server_running": True,
            "allow_system_table_mods": True,
            "before": before,
            "after": after_injection,
            "fake_version": fake_version,
        },
        "observed": {
            "checksum": checksum,
            "amcheck": before_amcheck,
            "business_invariants": before_business,
        },
        "recovery": {
            "strategy": "separate-working-copy",
            "steps": steps,
            "elapsed_ms": round(
                (time.monotonic_ns() - started) / 1_000_000,
                3,
            ),
            "reindex_before_refresh": [
                row["action"] for row in steps
            ] == [
                "REINDEX INDEX public.pg36_ch35_code_idx",
                "ALTER COLLATION public.pg36_ch35_icu REFRESH VERSION",
            ],
            "collation": repaired_collation,
            "amcheck": repaired_amcheck,
            "business_invariants": repaired_business,
            "business_invariants_match": repaired_business == baseline,
            "checksum": repaired_checksum,
        },
        "evidence_copy": {
            "preserved_until_final_cleanup": (
                case_digest_before == case_digest_after
                and case_dir.exists()
            ),
            "digest_before_working_copy": case_digest_before,
            "digest_after_working_copy": case_digest_after,
        },
    }


try:
    root.mkdir(mode=0o700)
    marker.write_text(run_id + "\n", encoding="utf-8")
    marker.chmod(0o600)
    socket_dir.mkdir(mode=0o700)
    run(
        [
            initdb,
            "-D",
            str(source_data),
            "--data-checksums",
            "--no-locale",
            "--encoding=UTF8",
            "--auth-local=trust",
            "--auth-host=reject",
        ],
        timeout=120,
    )
    with (source_data / "postgresql.conf").open(
        "a",
        encoding="utf-8",
    ) as stream:
        stream.write(
            "\n"
            "listen_addresses = ''\n"
            "port = " + str(port) + "\n"
            "unix_socket_directories = '" + str(socket_dir) + "'\n"
            "unix_socket_permissions = 0700\n"
            "allow_system_table_mods = on\n"
            "ignore_checksum_failure = off\n"
            "zero_damaged_pages = off\n"
            "max_parallel_workers_per_gather = 0\n"
        )
    start(source_data, "source")
    psql(
        """
        CREATE EXTENSION amcheck WITH SCHEMA public;
        CREATE COLLATION public.pg36_ch35_icu (
            provider = icu,
            locale = 'und',
            deterministic = true
        );
        CREATE TABLE public.pg36_ch35_accounts (
            id integer PRIMARY KEY,
            code text COLLATE public.pg36_ch35_icu NOT NULL,
            balance bigint NOT NULL,
            payload text NOT NULL
        );
        INSERT INTO public.pg36_ch35_accounts(
            id,
            code,
            balance,
            payload
        )
        SELECT g,
               'acct-' || lpad(g::text, 8, '0'),
               (g::bigint * 17) %% 100000,
               repeat(md5(g::text), 12)
        FROM generate_series(1, %d) AS g;
        CREATE INDEX pg36_ch35_code_idx
        ON public.pg36_ch35_accounts (
            code COLLATE public.pg36_ch35_icu
        );
        ANALYZE public.pg36_ch35_accounts;
        CHECKPOINT;
        """
        % int(CONFIG["row_count"]),
        timeout=180,
    )
    engine = sql_json(
        """
        SELECT json_build_object(
            'server_version', current_setting('server_version'),
            'data_checksums', current_setting('data_checksums'),
            'allow_system_table_mods',
                current_setting('allow_system_table_mods'),
            'ignore_checksum_failure',
                current_setting('ignore_checksum_failure'),
            'zero_damaged_pages',
                current_setting('zero_damaged_pages'),
            'listen_addresses',
                current_setting('listen_addresses'),
            'port', current_setting('port')::int
        )
        """,
        "engine projection",
    )
    if (
        not str(engine["server_version"]).startswith(
            CONFIG["postgresql_observed"]
        )
        or engine["data_checksums"] != "on"
        or engine["allow_system_table_mods"] != "on"
        or engine["ignore_checksum_failure"] != "off"
        or engine["zero_damaged_pages"] != "off"
        or engine["listen_addresses"] != ""
        or engine["port"] != port
    ):
        raise ExerciseError(
            "disposable engine settings drifted: "
            + json.dumps(engine, sort_keys=True)
        )
    baseline = business_invariants()
    relation = relation_projection()
    source_collation = collation_projection()
    source_amcheck = amcheck()
    if (
        baseline["row_count"] != int(CONFIG["row_count"])
        or relation["heap_blocks"] < int(CONFIG["minimum_heap_blocks"])
        or source_collation["version_mismatch"] is not False
        or source_collation["provider"] != "i"
        or source_amcheck["structural_check_passed"] is not True
    ):
        raise ExerciseError("clean source fixture did not validate")
    stop()
    source_checksum = checksum_projection(source_data)
    if source_checksum["offline_bad_checksums"] != 0:
        raise ExerciseError("clean source checksum validation failed")
    copy_cluster(source_data, golden_data)
    golden_before = tree_digest(golden_data)

    scenarios = ["PHYSICAL_HEAP_PAGE", "COLLATION_METADATA"]
    secrets.SystemRandom().shuffle(scenarios)
    cases = []
    for scenario in scenarios:
        case_id = "case-" + secrets.token_hex(6)
        if scenario == "PHYSICAL_HEAP_PAGE":
            cases.append(
                run_physical(case_id, baseline, relation)
            )
        else:
            cases.append(run_collation(case_id, baseline))

    golden_after = tree_digest(golden_data)
    if golden_before != golden_after:
        raise ExerciseError("known-good snapshot changed during recovery")
    result = {
        "schema": "pg36-ch35-exercise-v1",
        "run_id": run_id,
        "started_at": CONFIG["started_at"],
        "finished_at": utc_now(),
        "target": CONFIG["target"],
        "host": CONFIG["host"],
        "disposable": {
            "root": str(root),
            "port": port,
            "listen_addresses": "",
            "unix_socket_only": True,
            "data_checksums": True,
            "managed_patroni_member": False,
            "managed_dcs_member": False,
            "managed_service_route": False,
        },
        "engine": engine,
        "fixture": {
            "business_invariants": baseline,
            "relation": relation,
            "collation": source_collation,
            "amcheck": source_amcheck,
            "source_checksum": source_checksum,
        },
        "known_good_snapshot": {
            "stopped_copy": True,
            "digest_before_cases": golden_before,
            "digest_after_cases": golden_after,
            "unchanged": golden_before == golden_after,
        },
        "scenario_order": scenarios,
        "cases": cases,
        "blind_packets": [case["blind_packet"] for case in cases],
        "hidden_answers": [
            {
                "case_id": case["case_id"],
                "scenario": case["scenario"],
                "expected_route": case["expected_route"],
            }
            for case in cases
        ],
        "safety": {
            "managed_postgresql_mutated": False,
            "managed_pgdata_mutated": False,
            "managed_service_changed": False,
            "managed_route_changed": False,
            "managed_reset_host_executed": False,
            "unique_source_mutated": False,
            "manual_pg_wal_file_deletion": False,
            "ignore_checksum_failure_used": False,
            "zero_damaged_pages_used": False,
            "pg_resetwal_used": False,
            "wrong_action_executed": False,
            "production_data_touched": False,
            "production_traffic_touched": False,
            "external_dispatch_count": 0,
        },
    }
finally:
    if active_data is not None:
        try:
            stop()
        except Exception:
            pass
    if root.exists():
        marker_ok = (
            marker.is_file()
            and marker.read_text(encoding="utf-8").strip() == run_id
        )
        if (
            not marker_ok
            or not re.fullmatch(
                r"/tmp/pg36-ch35-forensics-[0-9a-f-]{36}",
                str(root),
            )
        ):
            raise ExerciseError("refusing unsafe forensic-root cleanup")
        shutil.rmtree(root)

if result is None:
    raise ExerciseError("exercise produced no result")
result["cleanup"] = {
    "exact_root": str(root),
    "marker_matched": True,
    "root_exists_after": root.exists(),
    "all_postmasters_stopped_before_cleanup": True,
}
print(json.dumps(result, sort_keys=True))
'''


def require_guards(args: argparse.Namespace, requirements: dict[str, Any]) -> None:
    if args.target_token != "pg36-l2-vagrant/pg-test":
        raise LabError("target token does not identify the chapter 35 sandbox")
    if args.confirmation != "CLONE_CLASSIFY_RECOVER_CH35":
        raise LabError("chapter 35 confirmation token is missing")
    if args.authority != "nonproduction-no-data-no-traffic":
        raise LabError("chapter 35 authority boundary drifted")
    target = requirements.get("target", {})
    risk = requirements.get("risk", {})
    forbidden = (
        "managed_postgresql_mutation_permitted",
        "managed_pgdata_mutation_permitted",
        "managed_service_change_permitted",
        "managed_route_change_permitted",
        "managed_reset_host_permitted",
        "unique_source_mutation_permitted",
        "manual_pg_wal_deletion_permitted",
        "ignore_checksum_failure_permitted",
        "zero_damaged_pages_permitted",
        "pg_resetwal_permitted",
    )
    if (
        target.get("id") != args.target_token
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or any(risk.get(key) is not False for key in forbidden)
    ):
        raise LabError("requirements do not preserve the forensic boundary")


def source_manifest(source_dir: Path) -> dict[str, Any]:
    rows = []
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file() or path.is_symlink():
            raise LabError(f"source file is missing or unsafe: {name}")
        rows.append(
            {
                "path": name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema": "pg36-ch35-source-manifest-v1",
        "generated_at": utc_now(),
        "files": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--authority", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        require_guards(args, requirements)
        if args.output.exists() and any(args.output.iterdir()):
            raise LabError("refusing to overwrite non-empty exercise directory")
        args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.chmod(0o700)
        run_id = str(uuid.UUID(bytes=secrets.token_bytes(16), version=4))
        config = {
            "run_id": run_id,
            "started_at": utc_now(),
            "target": requirements["target"]["id"],
            "host": requirements["disposable_cluster"]["host"],
            "root_prefix": requirements["disposable_cluster"][
                "root_prefix"
            ],
            "port": requirements["disposable_cluster"]["port"],
            "postgresql_observed": requirements["target"][
                "postgresql_observed"
            ],
            "row_count": requirements["fixture"]["row_count"],
            "minimum_heap_blocks": requirements["fixture"][
                "minimum_heap_blocks"
            ],
            "physical": requirements["physical_case"],
            "collation": requirements["collation_case"],
        }
        program = REMOTE_PROGRAM.replace(
            "__CONFIG_JSON__",
            repr(json.dumps(config, sort_keys=True)),
            1,
        )
        if "__CONFIG_JSON__" in program:
            raise LabError("remote configuration substitution failed")
        remote = run(
            ssh_base(
                args.ssh_user,
                str(requirements["target"]["observer_address"]),
            )
            + ["sudo", "-n", "-iu", "postgres", "python3", "-"],
            stdin=program,
            timeout=600,
        )
        try:
            evidence = json.loads(remote.stdout)
        except json.JSONDecodeError as exc:
            raise LabError("remote forensic exercise returned invalid JSON") from exc
        if not isinstance(evidence, dict):
            raise LabError("remote forensic exercise returned no object")
        if evidence.get("run_id") != run_id:
            raise LabError("remote forensic run identity drifted")
        write_json(args.output / "exercise-evidence.json", evidence)
        write_json(
            args.output / "blind-packets.json",
            evidence["blind_packets"],
        )
        write_json(
            args.output / "hidden-answers.json",
            evidence["hidden_answers"],
        )
        write_json(args.output / "cleanup.json", evidence["cleanup"])
        write_json(
            args.output / "source-manifest.json",
            source_manifest(args.source_dir),
        )
        write_json(
            args.output / "run-manifest.json",
            {
                "schema": "pg36-ch35-run-manifest-v1",
                "run_id": run_id,
                "created_at": utc_now(),
                "target": requirements["target"]["id"],
                "exercise_host": requirements["disposable_cluster"][
                    "host"
                ],
                "scenario_order": evidence["scenario_order"],
                "blind_case_ids": [
                    row["case_id"] for row in evidence["blind_packets"]
                ],
                "managed_reset_host_executed": False,
                "production_ch35_gate": "pending",
            },
        )
    except (
        KeyError,
        TypeError,
        OSError,
        LabError,
    ) as exc:
        print(f"exercise failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
