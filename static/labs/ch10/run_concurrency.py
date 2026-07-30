#!/usr/bin/env python3
"""Run deterministic PostgreSQL concurrency cases with psql workers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


NAMESPACE = 3610
WAIT_TIMEOUT = 15.0
PROCESS_TIMEOUT = 25.0


class LabError(RuntimeError):
    pass


@dataclass
class Worker:
    name: str
    app_name: str
    process: subprocess.Popen[str]
    stdout_path: Path
    stderr_path: Path
    stdout_handle: Any
    stderr_handle: Any

    def wait(self, timeout: float = PROCESS_TIMEOUT) -> int:
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self.stop()
            raise LabError(f"worker timed out: {self.name}") from exc
        finally:
            self.stdout_handle.close()
            self.stderr_handle.close()
        return code

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


class GateSession:
    def __init__(
        self,
        lab: "ConcurrencyLab",
        name: str,
        gates: Iterable[int],
    ) -> None:
        self.lab = lab
        self.name = name
        self.app_name = f"pg36-ch10-gate-{name}"
        self.gates = list(gates)
        self.stdout_path = lab.evidence / f"{name}-gate.stdout"
        self.stderr_path = lab.evidence / f"{name}-gate.stderr"
        self.stdout_handle = self.stdout_path.open("w", encoding="utf-8")
        self.stderr_handle = self.stderr_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            lab.psql_base(self.app_name),
            stdin=subprocess.PIPE,
            stdout=self.stdout_handle,
            stderr=self.stderr_handle,
            text=True,
        )
        if self.process.stdin is None:
            raise LabError("gate psql has no stdin")
        for gate in self.gates:
            self.send(
                f"SELECT pg_catalog.pg_advisory_lock"
                f"({NAMESPACE}, {gate});"
            )
        lab.wait_until(
            lambda: lab.granted_advisory_count(self.app_name)
            == len(self.gates),
            f"gate acquisition for {name}",
        )

    def send(self, sql: str) -> None:
        if self.process.poll() is not None:
            raise LabError(f"gate session exited early: {self.name}")
        assert self.process.stdin is not None
        self.process.stdin.write(sql + "\n")
        self.process.stdin.flush()

    def release(self) -> None:
        for gate in self.gates:
            self.send(
                f"SELECT pg_catalog.pg_advisory_unlock"
                f"({NAMESPACE}, {gate});"
            )
        self.lab.wait_until(
            lambda: self.lab.granted_advisory_count(self.app_name) == 0,
            f"gate release for {self.name}",
        )

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.send("SELECT pg_catalog.pg_advisory_unlock_all();")
                self.send("\\q")
                self.process.wait(timeout=5)
            except (LabError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.stdout_handle.close()
        self.stderr_handle.close()

    def __enter__(self) -> "GateSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


class ConcurrencyLab:
    def __init__(self, script_dir: Path, evidence: Path, service: str):
        self.script_dir = script_dir
        self.evidence = evidence
        self.service = service
        self.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.result: dict[str, Any] = {
            "schema": "pg36-ch10-concurrency-result-v1",
            "status": "running",
        }

    def psql_base(self, app_name: str) -> list[str]:
        return [
            "psql",
            "-X",
            "-w",
            "-qAt",
            f"--dbname=service={self.service} application_name={app_name}",
            "--set=ON_ERROR_STOP=1",
            "--set=VERBOSITY=verbose",
        ]

    def run_sql(
        self,
        sql: str,
        *,
        app_name: str = "pg36-ch10-controller",
        csv: bool = False,
        output: Path | None = None,
        expected: Iterable[int] = (0,),
    ) -> subprocess.CompletedProcess[str]:
        command = self.psql_base(app_name)
        if csv:
            command.extend(
                [
                    "--csv",
                    "--pset=tuples_only=off",
                    "--pset=footer=off",
                ]
            )
        command.extend(["--command", sql])
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PROCESS_TIMEOUT,
        )
        if output is not None:
            output.write_text(completed.stdout, encoding="utf-8")
            output.with_suffix(output.suffix + ".stderr").write_text(
                completed.stderr,
                encoding="utf-8",
            )
        if completed.returncode not in set(expected):
            raise LabError(
                f"psql {app_name} exit={completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        return completed

    def scalar(self, sql: str) -> str:
        completed = self.run_sql(sql)
        lines = [
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        if len(lines) != 1:
            raise LabError(
                f"expected one scalar row, got {len(lines)}: {lines}"
            )
        return lines[0]

    def json_value(self, sql: str) -> dict[str, Any]:
        try:
            value = json.loads(self.scalar(sql))
        except json.JSONDecodeError as exc:
            raise LabError("controller query did not return JSON") from exc
        if not isinstance(value, dict):
            raise LabError("controller JSON value is not an object")
        return value

    def execute_owner(self, sql: str) -> None:
        self.run_sql(
            "SET ROLE pg36_owner; "
            "SET search_path = pg_catalog, shop_private; "
            + sql
        )

    def wait_until(
        self,
        predicate: Any,
        description: str,
        timeout: float = WAIT_TIMEOUT,
    ) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except (LabError, ValueError) as exc:
                last_error = exc
            time.sleep(0.05)
        suffix = f": {last_error}" if last_error else ""
        raise LabError(f"timed out waiting for {description}{suffix}")

    def granted_advisory_count(self, app_name: str) -> int:
        return int(
            self.scalar(
                """
                SELECT count(*)
                FROM pg_catalog.pg_locks AS lock
                JOIN pg_catalog.pg_stat_activity AS activity
                  ON activity.pid = lock.pid
                WHERE activity.application_name = """
                + self.sql_literal(app_name)
                + """
                  AND lock.locktype = 'advisory'
                  AND lock.granted;
                """
            )
        )

    @staticmethod
    def sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def waiting_apps(self, app_names: Iterable[str]) -> int:
        values = ", ".join(
            self.sql_literal(name) for name in app_names
        )
        return int(
            self.scalar(
                f"""
                SELECT count(*)
                FROM pg_catalog.pg_stat_activity
                WHERE application_name IN ({values})
                  AND state = 'active'
                  AND wait_event_type = 'Lock'
                  AND wait_event = 'advisory';
                """
            )
        )

    def wait_advisory(self, workers: Iterable[Worker]) -> None:
        worker_list = list(workers)
        self.wait_until(
            lambda: self.waiting_apps(
                worker.app_name for worker in worker_list
            )
            == len(worker_list),
            "workers at advisory barrier",
        )

    def start_worker(
        self,
        name: str,
        sql_file: str,
        variables: dict[str, str | int | bool],
    ) -> Worker:
        app_name = f"pg36-ch10-{name}"
        stdout_path = self.evidence / f"{name}.stdout"
        stderr_path = self.evidence / f"{name}.stderr"
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        command = self.psql_base(app_name)
        for key, value in variables.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = str(value)
            command.append(f"--set={key}={rendered}")
        command.extend(["--file", str(self.script_dir / sql_file)])
        process = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        return Worker(
            name,
            app_name,
            process,
            stdout_path,
            stderr_path,
            stdout_handle,
            stderr_handle,
        )

    @staticmethod
    def wait_codes(workers: Iterable[Worker]) -> list[int]:
        return [worker.wait() for worker in workers]

    @staticmethod
    def text(worker: Worker) -> str:
        return worker.stdout_path.read_text(encoding="utf-8")

    @staticmethod
    def error_text(worker: Worker) -> str:
        return worker.stderr_path.read_text(encoding="utf-8")

    @staticmethod
    def one_sqlstate(workers: Iterable[Worker], sqlstate: str) -> bool:
        marker = f"ERROR:  {sqlstate}:"
        return sum(
            marker in ConcurrencyLab.error_text(worker)
            for worker in workers
        ) == 1

    def capture_csv(self, name: str, sql: str) -> None:
        self.run_sql(
            sql,
            app_name=f"pg36-ch10-observer-{name}",
            csv=True,
            output=self.evidence / f"{name}.csv",
        )

    def reset_inventory(self) -> None:
        self.execute_owner(
            """
            UPDATE shop_private.ch10_inventory
            SET available = 100,
                version = 0,
                updated_at = timestamptz '2025-01-01 00:00:00+00';
            """
        )

    def inventory_state(self) -> dict[str, Any]:
        return self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'available', available,
                'version', version
            )
            FROM shop_private.ch10_inventory
            WHERE sku_id = 1001;
            """
        )

    def reset_doctors(self) -> None:
        self.execute_owner(
            "UPDATE shop_private.ch10_doctor SET on_call = true;"
        )

    def doctor_state(self) -> dict[str, Any]:
        return self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'on_call', count(*) FILTER (WHERE on_call),
                'off_call', count(*) FILTER (WHERE NOT on_call)
            )
            FROM shop_private.ch10_doctor;
            """
        )

    def assert_fixture(self) -> None:
        ok = self.scalar(
            """
            SELECT count(*) = 6
               AND bool_and(
                   pg_catalog.obj_description(
                       relation.oid,
                       'pg_class'
                   ) =
                   'pg36 ch10 deterministic concurrency lab; safe to rebuild'
               )
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'shop_private'
              AND relation.relname IN (
                  'ch10_inventory',
                  'ch10_doctor',
                  'ch10_deadlock_probe',
                  'ch10_job',
                  'ch10_payment_request',
                  'ch10_outbox'
              );
            """
        )
        if ok != "t":
            raise LabError("ch10 fixture marker verification failed")

    def run_lost_and_safe_updates(self) -> None:
        self.reset_inventory()
        lost_workers: list[Worker] = []
        with GateSession(self, "lost", [1001]) as gate:
            lost_workers = [
                self.start_worker(
                    "lost-a",
                    "lost-update-worker.sql",
                    {"worker": "a", "qty": 10, "gate": 1001},
                ),
                self.start_worker(
                    "lost-b",
                    "lost-update-worker.sql",
                    {"worker": "b", "qty": 20, "gate": 1001},
                ),
            ]
            self.wait_advisory(lost_workers)
            self.capture_csv(
                "lost-waiting",
                """
                SELECT application_name, state,
                       wait_event_type, wait_event
                FROM pg_catalog.pg_stat_activity
                WHERE application_name IN (
                    'pg36-ch10-lost-a',
                    'pg36-ch10-lost-b'
                )
                ORDER BY application_name;
                """,
            )
            gate.release()
            lost_codes = self.wait_codes(lost_workers)
        lost_state = self.inventory_state()
        lost_observed = all(
            "observed=100" in self.text(worker)
            for worker in lost_workers
        )
        lost_actual = int(lost_state["available"])
        if (
            lost_codes != [0, 0]
            or not lost_observed
            or lost_actual not in {80, 90}
            or int(lost_state["version"]) != 2
        ):
            raise LabError("Read Committed lost-update case drifted")

        self.reset_inventory()
        atomic_workers: list[Worker] = []
        with GateSession(self, "atomic", [1002]) as gate:
            atomic_workers = [
                self.start_worker(
                    "atomic-a",
                    "atomic-update-worker.sql",
                    {"worker": "a", "qty": 10, "gate": 1002},
                ),
                self.start_worker(
                    "atomic-b",
                    "atomic-update-worker.sql",
                    {"worker": "b", "qty": 20, "gate": 1002},
                ),
            ]
            self.wait_advisory(atomic_workers)
            gate.release()
            atomic_codes = self.wait_codes(atomic_workers)
        atomic_state = self.inventory_state()
        if (
            atomic_codes != [0, 0]
            or int(atomic_state["available"]) != 70
            or int(atomic_state["version"]) != 2
            or not all(
                "/updated=1/" in self.text(worker)
                for worker in atomic_workers
            )
        ):
            raise LabError("atomic-update case drifted")

        self.reset_inventory()
        optimistic_workers: list[Worker] = []
        quantities = {"optimistic-a": 10, "optimistic-b": 20}
        with GateSession(self, "optimistic", [1003]) as gate:
            optimistic_workers = [
                self.start_worker(
                    "optimistic-a",
                    "optimistic-worker.sql",
                    {"worker": "a", "qty": 10, "gate": 1003},
                ),
                self.start_worker(
                    "optimistic-b",
                    "optimistic-worker.sql",
                    {"worker": "b", "qty": 20, "gate": 1003},
                ),
            ]
            self.wait_advisory(optimistic_workers)
            gate.release()
            optimistic_codes = self.wait_codes(optimistic_workers)
        first_state = self.inventory_state()
        conflicts = [
            worker
            for worker in optimistic_workers
            if "/updated=0/" in self.text(worker)
        ]
        successes = [
            worker
            for worker in optimistic_workers
            if "/updated=1/" in self.text(worker)
        ]
        if (
            optimistic_codes != [0, 0]
            or len(conflicts) != 1
            or len(successes) != 1
            or int(first_state["available"]) not in {80, 90}
            or int(first_state["version"]) != 1
        ):
            raise LabError("optimistic first attempt drifted")
        loser = conflicts[0]
        retry = self.start_worker(
            "optimistic-retry",
            "optimistic-retry.sql",
            {
                "worker": loser.name,
                "qty": quantities[loser.name],
            },
        )
        retry_code = retry.wait()
        retry_state = self.inventory_state()
        if (
            retry_code != 0
            or int(retry_state["available"]) != 70
            or int(retry_state["version"]) != 2
            or "retry_updated=1" not in self.text(retry)
        ):
            raise LabError("optimistic retry drifted")

        self.result["lost_update"] = {
            "isolation": "read committed",
            "both_observed": 100,
            "requested_total": 30,
            "serial_expected": 70,
            "actual": lost_actual,
            "lost_update_observed": True,
        }
        self.result["atomic_update"] = {
            "successful_writes": 2,
            "actual": 70,
            "version": 2,
            "invariant_preserved": True,
        }
        self.result["optimistic_update"] = {
            "first_attempt_successes": 1,
            "first_attempt_conflicts": 1,
            "retry_successes": 1,
            "actual": 70,
            "version": 2,
            "invariant_preserved": True,
        }

    def run_isolation(self) -> None:
        self.reset_inventory()
        rr_workers: list[Worker] = []
        with GateSession(self, "repeatable-update", [1004]) as gate:
            rr_workers = [
                self.start_worker(
                    "rr-update-a",
                    "repeatable-update-worker.sql",
                    {"worker": "a", "qty": 10, "gate": 1004},
                ),
                self.start_worker(
                    "rr-update-b",
                    "repeatable-update-worker.sql",
                    {"worker": "b", "qty": 20, "gate": 1004},
                ),
            ]
            self.wait_advisory(rr_workers)
            gate.release()
            rr_codes = self.wait_codes(rr_workers)
        rr_state = self.inventory_state()
        if (
            sorted(rr_codes) != [0, 3]
            or not self.one_sqlstate(rr_workers, "40001")
            or int(rr_state["available"]) not in {80, 90}
            or int(rr_state["version"]) != 1
        ):
            raise LabError("Repeatable Read write-conflict case drifted")

        self.reset_doctors()
        skew_workers: list[Worker] = []
        with GateSession(self, "write-skew-rr", [1005]) as gate:
            skew_workers = [
                self.start_worker(
                    "write-skew-rr-a",
                    "doctor-worker.sql",
                    {
                        "worker": "a",
                        "doctor_id": 1,
                        "gate": 1005,
                        "serializable": False,
                    },
                ),
                self.start_worker(
                    "write-skew-rr-b",
                    "doctor-worker.sql",
                    {
                        "worker": "b",
                        "doctor_id": 2,
                        "gate": 1005,
                        "serializable": False,
                    },
                ),
            ]
            self.wait_advisory(skew_workers)
            gate.release()
            skew_codes = self.wait_codes(skew_workers)
        skew_state = self.doctor_state()
        if (
            skew_codes != [0, 0]
            or int(skew_state["on_call"]) != 0
            or not all(
                "observed_on_call=2" in self.text(worker)
                for worker in skew_workers
            )
        ):
            raise LabError("Repeatable Read write-skew case drifted")

        self.reset_doctors()
        serial_workers: list[Worker] = []
        with GateSession(self, "write-skew-serial", [1006]) as gate:
            serial_workers = [
                self.start_worker(
                    "write-skew-ser-a",
                    "doctor-worker.sql",
                    {
                        "worker": "a",
                        "doctor_id": 1,
                        "gate": 1006,
                        "serializable": True,
                    },
                ),
                self.start_worker(
                    "write-skew-ser-b",
                    "doctor-worker.sql",
                    {
                        "worker": "b",
                        "doctor_id": 2,
                        "gate": 1006,
                        "serializable": True,
                    },
                ),
            ]
            self.wait_advisory(serial_workers)
            self.capture_csv(
                "serializable-siread",
                """
                SELECT activity.application_name,
                       lock.locktype,
                       lock.mode,
                       lock.relation::regclass AS relation_name,
                       lock.page,
                       lock.tuple
                FROM pg_catalog.pg_locks AS lock
                JOIN pg_catalog.pg_stat_activity AS activity
                  ON activity.pid = lock.pid
                WHERE activity.application_name IN (
                    'pg36-ch10-write-skew-ser-a',
                    'pg36-ch10-write-skew-ser-b'
                )
                  AND lock.mode = 'SIReadLock'
                ORDER BY activity.application_name,
                         lock.locktype,
                         lock.relation,
                         lock.page,
                         lock.tuple;
                """,
            )
            siread_count = int(
                self.scalar(
                    """
                    SELECT count(*)
                    FROM pg_catalog.pg_locks AS lock
                    JOIN pg_catalog.pg_stat_activity AS activity
                      ON activity.pid = lock.pid
                    WHERE activity.application_name IN (
                        'pg36-ch10-write-skew-ser-a',
                        'pg36-ch10-write-skew-ser-b'
                    )
                      AND lock.mode = 'SIReadLock';
                    """
                )
            )
            gate.release()
            serial_codes = self.wait_codes(serial_workers)
        serial_state = self.doctor_state()
        if (
            sorted(serial_codes) != [0, 3]
            or not self.one_sqlstate(serial_workers, "40001")
            or int(serial_state["on_call"]) != 1
            or siread_count < 2
        ):
            raise LabError("Serializable write-skew case drifted")

        self.result["repeatable_read_write_conflict"] = {
            "successes": 1,
            "sqlstate_40001": 1,
            "actual_after_one_commit": int(rr_state["available"]),
            "silent_overwrite": False,
        }
        self.result["repeatable_read_write_skew"] = {
            "commits": 2,
            "observed_on_call_each": 2,
            "final_on_call": 0,
            "invariant_violated": True,
        }
        self.result["serializable_write_skew"] = {
            "commits": 1,
            "sqlstate_40001": 1,
            "siread_locks_observed": siread_count,
            "final_on_call": 1,
            "invariant_preserved": True,
        }

    def lock_waiting_on_holder(self) -> bool:
        value = self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'wait_event_type', waiter.wait_event_type,
                'wait_event', waiter.wait_event,
                'blockers',
                    pg_catalog.cardinality(
                        pg_catalog.pg_blocking_pids(waiter.pid)
                    )
            )
            FROM pg_catalog.pg_stat_activity AS waiter
            WHERE waiter.application_name =
                  'pg36-ch10-row-lock-waiter';
            """
        )
        return (
            value.get("wait_event_type") == "Lock"
            and int(value.get("blockers", 0)) == 1
        )

    def run_locking(self) -> None:
        self.reset_inventory()
        nowait_holder: Worker
        with GateSession(self, "nowait", [1008]) as gate:
            nowait_holder = self.start_worker(
                "nowait-holder",
                "row-lock-holder.sql",
                {"gate": 1008},
            )
            self.wait_advisory([nowait_holder])
            nowait = self.start_worker(
                "nowait-probe",
                "nowait-worker.sql",
                {},
            )
            nowait_code = nowait.wait()
            if (
                nowait_code != 3
                or "ERROR:  55P03:" not in self.error_text(nowait)
            ):
                raise LabError("NOWAIT did not fail with 55P03")
            gate.release()
            if nowait_holder.wait() != 0:
                raise LabError("NOWAIT holder did not finish")

        self.execute_owner(
            """
            UPDATE shop_private.ch10_job
            SET job_state = 'queued',
                claimed_by = NULL,
                claimed_at = NULL;
            """
        )
        job_workers: list[Worker] = []
        with GateSession(self, "skip-locked", [1009, 1010]) as gate:
            first = self.start_worker(
                "job-a",
                "job-worker.sql",
                {"worker": "worker-a", "gate": 1009},
            )
            self.wait_advisory([first])
            second = self.start_worker(
                "job-b",
                "job-worker.sql",
                {"worker": "worker-b", "gate": 1010},
            )
            self.wait_advisory([first, second])
            job_workers = [first, second]
            gate.release()
            job_codes = self.wait_codes(job_workers)
        claimed_sets: list[set[int]] = []
        for worker in job_workers:
            match = re.search(r"claimed=([0-9,]+)", self.text(worker))
            if not match:
                raise LabError(f"missing claimed jobs: {worker.name}")
            claimed_sets.append(
                {int(value) for value in match.group(1).split(",")}
            )
        job_state = self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'running', count(*) FILTER (
                    WHERE job_state = 'running'
                ),
                'worker_a', count(*) FILTER (
                    WHERE claimed_by = 'worker-a'
                ),
                'worker_b', count(*) FILTER (
                    WHERE claimed_by = 'worker-b'
                )
            )
            FROM shop_private.ch10_job;
            """
        )
        if (
            job_codes != [0, 0]
            or claimed_sets[0] & claimed_sets[1]
            or claimed_sets[0] | claimed_sets[1] != set(range(1, 7))
            or int(job_state["running"]) != 6
            or sorted(
                [
                    int(job_state["worker_a"]),
                    int(job_state["worker_b"]),
                ]
            )
            != [3, 3]
        ):
            raise LabError("SKIP LOCKED queue case drifted")

        self.execute_owner(
            "UPDATE shop_private.ch10_deadlock_probe SET value = 0;"
        )
        deadlock_workers: list[Worker] = []
        with GateSession(self, "deadlock", [1011, 1012]) as gate:
            deadlock_workers = [
                self.start_worker(
                    "deadlock-a",
                    "deadlock-worker.sql",
                    {
                        "worker": "a",
                        "first_row": 1,
                        "second_row": 2,
                        "gate": 1011,
                    },
                ),
                self.start_worker(
                    "deadlock-b",
                    "deadlock-worker.sql",
                    {
                        "worker": "b",
                        "first_row": 2,
                        "second_row": 1,
                        "gate": 1012,
                    },
                ),
            ]
            self.wait_advisory(deadlock_workers)
            self.capture_csv(
                "deadlock-before-release",
                """
                SELECT activity.application_name,
                       lock.locktype,
                       lock.mode,
                       lock.granted,
                       lock.relation::regclass AS relation_name,
                       lock.transactionid
                FROM pg_catalog.pg_locks AS lock
                JOIN pg_catalog.pg_stat_activity AS activity
                  ON activity.pid = lock.pid
                WHERE activity.application_name IN (
                    'pg36-ch10-deadlock-a',
                    'pg36-ch10-deadlock-b'
                )
                ORDER BY activity.application_name,
                         lock.locktype,
                         lock.mode,
                         lock.granted;
                """,
            )
            gate.release()
            deadlock_codes = self.wait_codes(deadlock_workers)
        deadlock_state = self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'row1', max(value) FILTER (WHERE row_id = 1),
                'row2', max(value) FILTER (WHERE row_id = 2)
            )
            FROM shop_private.ch10_deadlock_probe;
            """
        )
        if (
            sorted(deadlock_codes) != [0, 3]
            or not self.one_sqlstate(deadlock_workers, "40P01")
            or int(deadlock_state["row1"]) != 1
            or int(deadlock_state["row2"]) != 1
        ):
            raise LabError("deadlock case drifted")

        session_lock = GateSession(self, "advisory-session", [])
        try:
            session_lock.send("BEGIN;")
            session_lock.send(
                f"SELECT pg_catalog.pg_advisory_lock"
                f"({NAMESPACE}, 1015);"
            )
            self.wait_until(
                lambda: self.granted_advisory_count(
                    session_lock.app_name
                )
                == 1,
                "session advisory lock",
            )
            session_lock.send("ROLLBACK;")
            self.wait_until(
                lambda: self.scalar(
                    """
                    SELECT xact_start IS NULL
                    FROM pg_catalog.pg_stat_activity
                    WHERE application_name =
                          'pg36-ch10-gate-advisory-session';
                    """
                )
                == "t",
                "session advisory rollback completion",
            )
            session_survived = (
                self.granted_advisory_count(session_lock.app_name) == 1
            )
            session_lock.send(
                f"SELECT pg_catalog.pg_advisory_unlock"
                f"({NAMESPACE}, 1015);"
            )
            self.wait_until(
                lambda: self.granted_advisory_count(
                    session_lock.app_name
                )
                == 0,
                "session advisory unlock",
            )
        finally:
            session_lock.close()

        xact_lock = GateSession(self, "advisory-xact", [])
        try:
            xact_lock.send("BEGIN;")
            xact_lock.send(
                f"SELECT pg_catalog.pg_advisory_xact_lock"
                f"({NAMESPACE}, 1016);"
            )
            self.wait_until(
                lambda: self.granted_advisory_count(
                    xact_lock.app_name
                )
                == 1,
                "transaction advisory lock",
            )
            xact_lock.send("COMMIT;")
            self.wait_until(
                lambda: self.granted_advisory_count(
                    xact_lock.app_name
                )
                == 0,
                "transaction advisory release",
            )
            xact_released = True
        finally:
            xact_lock.close()
        if not session_survived or not xact_released:
            raise LabError("advisory lock lifecycle drifted")

        self.reset_inventory()
        row_workers: list[Worker] = []
        with GateSession(self, "row-lock", [1007]) as gate:
            holder = self.start_worker(
                "row-lock-holder",
                "row-lock-holder.sql",
                {"gate": 1007},
            )
            self.wait_advisory([holder])
            waiter = self.start_worker(
                "row-lock-waiter",
                "row-lock-waiter.sql",
                {},
            )
            self.wait_until(
                self.lock_waiting_on_holder,
                "row-lock waiter and blocker edge",
            )
            self.capture_csv(
                "row-lock-graph",
                """
                SELECT
                    waiter.pid AS waiter_pid,
                    waiter.backend_start AS waiter_backend_start,
                    waiter.application_name AS waiter_application,
                    waiter.state AS waiter_state,
                    waiter.wait_event_type,
                    waiter.wait_event,
                    blocker.pid AS blocker_pid,
                    blocker.backend_start AS blocker_backend_start,
                    blocker.application_name AS blocker_application,
                    blocker.state AS blocker_state,
                    blocker.wait_event_type AS blocker_wait_event_type,
                    blocker.wait_event AS blocker_wait_event
                FROM pg_catalog.pg_stat_activity AS waiter
                CROSS JOIN LATERAL pg_catalog.unnest(
                    pg_catalog.pg_blocking_pids(waiter.pid)
                ) AS edge(blocker_pid)
                JOIN pg_catalog.pg_stat_activity AS blocker
                  ON blocker.pid = edge.blocker_pid
                WHERE waiter.application_name =
                      'pg36-ch10-row-lock-waiter';
                """,
            )
            blocker_count = int(
                self.scalar(
                    """
                    SELECT pg_catalog.cardinality(
                               pg_catalog.pg_blocking_pids(pid)
                           )
                    FROM pg_catalog.pg_stat_activity
                    WHERE application_name =
                          'pg36-ch10-row-lock-waiter';
                    """
                )
            )
            gate.release()
            row_workers = [holder, waiter]
            row_codes = self.wait_codes(row_workers)
        row_state = self.inventory_state()
        if (
            row_codes != [0, 0]
            or blocker_count != 1
            or int(row_state["available"]) != 70
            or int(row_state["version"]) != 2
            or "waiter=locked/available=90" not in self.text(waiter)
        ):
            raise LabError("row lock serialization case drifted")

        self.result["nowait"] = {
            "sqlstate_55P03": 1,
            "blocked_instead_of_waiting": True,
        }
        self.result["skip_locked"] = {
            "workers": 2,
            "claimed_each": [3, 3],
            "distinct_jobs": 6,
            "duplicate_claims": 0,
        }
        self.result["deadlock"] = {
            "sqlstate_40P01": 1,
            "commits": 1,
            "row_values": [1, 1],
            "state_consistent": True,
        }
        self.result["advisory_lifecycle"] = {
            "session_lock_survived_rollback": session_survived,
            "transaction_lock_released_at_end": xact_released,
        }
        self.result["row_lock"] = {
            "blocker_edges": blocker_count,
            "wait_event_type": "Lock",
            "waiter_saw_after_holder": 90,
            "final_available": 70,
            "invariant_preserved": True,
        }

    def run_idempotency(self) -> None:
        self.execute_owner(
            """
            DELETE FROM shop_private.ch10_outbox;
            DELETE FROM shop_private.ch10_payment_request;
            """
        )
        workers: list[Worker] = []
        with GateSession(self, "payment", [1013, 1014]) as gate:
            workers = [
                self.start_worker(
                    "payment-a",
                    "payment-worker.sql",
                    {"worker": "a", "gate": 1013},
                ),
                self.start_worker(
                    "payment-b",
                    "payment-worker.sql",
                    {"worker": "b", "gate": 1014},
                ),
            ]
            self.wait_advisory(workers)
            gate.release()
            codes = self.wait_codes(workers)
        texts = [self.text(worker) for worker in workers]
        inserted = sum("/inserted=1/" in value for value in texts)
        reused = sum("/inserted=0/" in value for value in texts)
        responses = {
            re.search(r"/response=(.+)$", value, re.MULTILINE).group(1)
            for value in texts
            if re.search(r"/response=(.+)$", value, re.MULTILINE)
        }
        state = self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'payments',
                    (SELECT count(*)
                     FROM shop_private.ch10_payment_request),
                'outbox',
                    (SELECT count(*)
                     FROM shop_private.ch10_outbox),
                'payment_id',
                    (SELECT min(payment_id)
                     FROM shop_private.ch10_payment_request)
            );
            """
        )
        mismatch = self.start_worker(
            "payment-mismatch",
            "payment-mismatch.sql",
            {},
        )
        mismatch_code = mismatch.wait()
        after_mismatch = self.json_value(
            """
            SELECT pg_catalog.json_build_object(
                'payments',
                    (SELECT count(*)
                     FROM shop_private.ch10_payment_request),
                'outbox',
                    (SELECT count(*)
                     FROM shop_private.ch10_outbox)
            );
            """
        )
        if (
            codes != [0, 0]
            or inserted != 1
            or reused != 1
            or len(responses) != 1
            or int(state["payments"]) != 1
            or int(state["outbox"]) != 1
            or state["payment_id"] not in {"pay-demo-a", "pay-demo-b"}
            or mismatch_code != 3
            or "ERROR:  P0001:" not in self.error_text(mismatch)
            or after_mismatch != {"payments": 1, "outbox": 1}
        ):
            raise LabError("payment idempotency case drifted")

        self.result["payment_idempotency"] = {
            "concurrent_requests": 2,
            "inserted": inserted,
            "reused": reused,
            "distinct_responses": len(responses),
            "payment_rows": 1,
            "outbox_rows": 1,
            "mismatch_sqlstate_P0001": 1,
            "external_call_inside_transaction": False,
        }

    def assert_cleanup(self) -> None:
        workers = int(
            self.scalar(
                """
                SELECT count(*)
                FROM pg_catalog.pg_stat_activity
                WHERE pid <> pg_catalog.pg_backend_pid()
                  AND datname = current_database()
                  AND application_name LIKE 'pg36-ch10-%';
                """
            )
        )
        advisory = int(
            self.scalar(
                f"""
                SELECT count(*)
                FROM pg_catalog.pg_locks
                WHERE locktype = 'advisory'
                  AND classid = {NAMESPACE}::oid
                  AND objid BETWEEN 1001::oid AND 1016::oid;
                """
            )
        )
        if workers != 0 or advisory != 0:
            raise LabError(
                f"cleanup failed: workers={workers} advisory={advisory}"
            )
        self.result["cleanup"] = {
            "active_workers": workers,
            "advisory_locks": advisory,
        }

    def write_result(self) -> None:
        self.result["status"] = "ok"
        path = self.evidence / "concurrency-result.json"
        path.write_text(
            json.dumps(self.result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=["lost", "isolation", "locking", "idempotency", "all"],
        default="all",
    )
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--service", default=os.environ.get("PGSERVICE", "pg36-admin"))
    args = parser.parse_args()

    if not os.environ.get("PGSERVICEFILE"):
        raise LabError("PGSERVICEFILE is required")

    lab = ConcurrencyLab(
        Path(__file__).resolve().parent,
        args.evidence_dir.resolve(),
        args.service,
    )
    lab.assert_fixture()
    if args.case in {"lost", "all"}:
        lab.run_lost_and_safe_updates()
    if args.case in {"isolation", "all"}:
        lab.run_isolation()
    if args.case in {"locking", "all"}:
        lab.run_locking()
    if args.case in {"idempotency", "all"}:
        lab.run_idempotency()
    lab.assert_cleanup()
    lab.write_result()
    print(f"status=ok case={args.case}")
    print(f"evidence={lab.evidence}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LabError, OSError, subprocess.SubprocessError) as exc:
        print(f"status=error error={exc}", file=sys.stderr)
        raise SystemExit(1)
