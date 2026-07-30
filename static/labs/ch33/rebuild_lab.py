#!/usr/bin/env python3
"""Run pg_rewind and fresh pg_basebackup against disposable clusters."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from common import LabError, read_json, run, ssh_base, write_json


REMOTE_EXERCISE = textwrap.dedent(
    r'''
    import argparse
    import hashlib
    import json
    import os
    import shutil
    import subprocess
    import sys
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    class ExerciseError(RuntimeError):
        pass

    def now():
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def execute(args, timeout=120):
        started = time.monotonic_ns()
        try:
            result = subprocess.run(
                [str(value) for value in args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExerciseError(f"cannot execute {args[0]}: {exc}") from exc
        finished = time.monotonic_ns()
        if result.returncode != 0:
            lines = result.stderr.strip().splitlines()
            detail = lines[-1] if lines else f"exit {result.returncode}"
            raise ExerciseError(f"command failed ({Path(args[0]).name}): {detail}")
        return result, {
            "duration_ms": (finished - started) / 1_000_000,
            "stdout_sha256": hashlib.sha256(
                result.stdout.encode("utf-8")
            ).hexdigest(),
            "stderr_sha256": hashlib.sha256(
                result.stderr.encode("utf-8")
            ).hexdigest(),
        }

    def append_config(data_dir, socket_dir, port):
        payload = "\n".join([
            "",
            "# pg36 chapter 33 disposable rebuild lab",
            "listen_addresses = ''",
            f"port = {port}",
            f"unix_socket_directories = '{socket_dir}'",
            "unix_socket_permissions = 0700",
            "wal_level = replica",
            "max_wal_senders = 5",
            "max_replication_slots = 5",
            "wal_keep_size = '64MB'",
            "wal_log_hints = on",
            "full_page_writes = on",
            "logging_collector = off",
            "log_min_messages = warning",
            "",
        ])
        with (data_dir / "postgresql.conf").open("a", encoding="utf-8") as stream:
            stream.write(payload)

    def options(socket_dir, port):
        return (
            f"-c unix_socket_directories='{socket_dir}' "
            f"-c port={port} -c listen_addresses=''"
        )

    def start(pg_ctl, data_dir, socket_dir, port):
        execute(
            [
                pg_ctl,
                "-D",
                data_dir,
                "-l",
                data_dir / "server.log",
                "-o",
                options(socket_dir, port),
                "-w",
                "start",
            ]
        )

    def stop(pg_ctl, data_dir):
        status = subprocess.run(
            [str(pg_ctl), "-D", str(data_dir), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if status.returncode == 0:
            execute([pg_ctl, "-D", data_dir, "-m", "fast", "-w", "stop"])

    def sql(psql, socket_dir, port, statement):
        result, _ = execute(
            [
                psql,
                "-X",
                "-qAt",
                "-h",
                socket_dir,
                "-p",
                str(port),
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                statement,
            ],
            timeout=60,
        )
        return result.stdout.strip()

    def wait_sql(psql, socket_dir, port, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = sql(psql, socket_dir, port, predicate)
                if last == "t":
                    return
            except ExerciseError:
                pass
            time.sleep(0.2)
        raise ExerciseError(f"SQL predicate did not become true: {last}")

    def facts(psql, socket_dir, port):
        raw = sql(
            psql,
            socket_dir,
            port,
            """
            SELECT json_build_object(
                'system_identifier',
                    (SELECT system_identifier::text FROM pg_control_system()),
                'timeline',
                    (SELECT timeline_id FROM pg_control_checkpoint()),
                'in_recovery', pg_is_in_recovery(),
                'data_checksums', current_setting('data_checksums'),
                'wal_log_hints', current_setting('wal_log_hints'),
                'full_page_writes', current_setting('full_page_writes'),
                'receiver_status',
                    COALESCE(
                        (SELECT status FROM pg_stat_wal_receiver LIMIT 1),
                        ''
                    ),
                'markers',
                    COALESCE(
                        (
                            SELECT json_agg(marker ORDER BY marker)
                            FROM pg36_ch33_lineage
                        ),
                        '[]'::json
                    )
            )
            """,
        )
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ExerciseError("SQL facts did not return an object")
        return value

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--root", type=Path, required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--source-port", type=int, required=True)
        parser.add_argument("--rewind-port", type=int, required=True)
        parser.add_argument("--basebackup-port", type=int, required=True)
        args = parser.parse_args()

        prefix = Path("/tmp/pg36-ch33-rebuild")
        if (
            args.root.parent != Path("/tmp")
            or not args.root.name.startswith(prefix.name + "-")
            or args.root.name != prefix.name + "-" + args.run_id
        ):
            raise ExerciseError("disposable root identity guard failed")
        if args.root.exists():
            raise ExerciseError("refusing to reuse disposable rebuild root")

        bindir_result, _ = execute(["pg_config", "--bindir"])
        bindir = Path(bindir_result.stdout.strip())
        binaries = {
            name: bindir / name
            for name in (
                "initdb",
                "pg_basebackup",
                "pg_ctl",
                "pg_rewind",
                "psql",
            )
        }
        if any(not path.is_file() for path in binaries.values()):
            raise ExerciseError("required PostgreSQL binary is missing")

        root = args.root
        a = root / "A"
        b = root / "B"
        c = root / "C"
        sa = root / "sock-A"
        sb = root / "sock-B"
        sc = root / "sock-C"
        transitions = []
        root.mkdir(mode=0o700)
        (root / ".pg36-ch33-owned").write_text(args.run_id + "\n")
        for socket in (sa, sb, sc):
            socket.mkdir(mode=0o700)

        result = {
            "schema": "pg36-ch33-rebuild-evidence-v1",
            "run_id": args.run_id,
            "started_at": now(),
            "root": str(root),
            "listen_addresses": "",
            "managed_pgdata_touched": False,
            "patroni_registered": False,
            "dcs_changed": False,
            "route_changed": False,
            "concurrent_divergent_primaries": False,
            "transitions": transitions,
        }
        running = set()
        try:
            _, init_metric = execute(
                [
                    binaries["initdb"],
                    "-D",
                    a,
                    "--data-checksums",
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--no-locale",
                    "--encoding=UTF8",
                ]
            )
            append_config(a, sa, args.source_port)
            start(binaries["pg_ctl"], a, sa, args.source_port)
            running.add("A")
            transitions.append({"event": "A-started-primary", "at": now()})
            sql(
                binaries["psql"],
                sa,
                args.source_port,
                """
                CREATE TABLE pg36_ch33_lineage (
                    marker text PRIMARY KEY,
                    origin text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
                );
                INSERT INTO pg36_ch33_lineage(marker, origin)
                VALUES ('base', 'A');
                CHECKPOINT;
                """,
            )
            a_base = facts(binaries["psql"], sa, args.source_port)

            _, base_b_metric = execute(
                [
                    binaries["pg_basebackup"],
                    "-h",
                    sa,
                    "-p",
                    str(args.source_port),
                    "-U",
                    "postgres",
                    "-D",
                    b,
                    "-X",
                    "stream",
                    "-R",
                    "--checkpoint=fast",
                    "--no-password",
                ],
                timeout=120,
            )
            start(binaries["pg_ctl"], b, sb, args.rewind_port)
            running.add("B")
            wait_sql(
                binaries["psql"],
                sb,
                args.rewind_port,
                "SELECT pg_is_in_recovery()",
            )
            transitions.append({"event": "B-streaming-from-A", "at": now()})

            stop(binaries["pg_ctl"], a)
            running.remove("A")
            transitions.append({"event": "A-stopped-before-B-promotion", "at": now()})
            execute([binaries["pg_ctl"], "-D", b, "-w", "promote"])
            wait_sql(
                binaries["psql"],
                sb,
                args.rewind_port,
                "SELECT NOT pg_is_in_recovery()",
            )
            sql(
                binaries["psql"],
                sb,
                args.rewind_port,
                """
                INSERT INTO pg36_ch33_lineage(marker, origin)
                VALUES ('new-primary', 'B');
                CHECKPOINT;
                """,
            )
            b_promoted = facts(binaries["psql"], sb, args.rewind_port)
            transitions.append({"event": "B-promoted-and-written", "at": now()})

            stop(binaries["pg_ctl"], b)
            running.remove("B")
            transitions.append({"event": "B-stopped-before-A-diverges", "at": now()})
            start(binaries["pg_ctl"], a, sa, args.source_port)
            running.add("A")
            sql(
                binaries["psql"],
                sa,
                args.source_port,
                """
                INSERT INTO pg36_ch33_lineage(marker, origin)
                VALUES ('old-primary-divergent', 'A');
                CHECKPOINT;
                """,
            )
            a_divergent = facts(binaries["psql"], sa, args.source_port)
            stop(binaries["pg_ctl"], a)
            running.remove("A")
            transitions.append({"event": "A-diverged-then-stopped", "at": now()})

            start(binaries["pg_ctl"], b, sb, args.rewind_port)
            running.add("B")
            sql(
                binaries["psql"],
                sb,
                args.rewind_port,
                """
                INSERT INTO pg36_ch33_lineage(marker, origin)
                VALUES ('after-divergence', 'B');
                CHECKPOINT;
                """,
            )
            transitions.append({"event": "B-restarted-as-only-primary", "at": now()})

            source_conn = (
                f"host={sb} port={args.rewind_port} "
                "dbname=postgres user=postgres"
            )
            _, rewind_metric = execute(
                [
                    binaries["pg_rewind"],
                    f"--target-pgdata={a}",
                    f"--source-server={source_conn}",
                    "--write-recovery-conf",
                    "--progress",
                ],
                timeout=120,
            )
            if not (a / "standby.signal").exists():
                raise ExerciseError("pg_rewind did not create standby.signal")
            start(binaries["pg_ctl"], a, sa, args.source_port)
            running.add("A")
            wait_sql(
                binaries["psql"],
                sa,
                args.source_port,
                """
                SELECT pg_is_in_recovery()
                   AND EXISTS (
                       SELECT 1 FROM pg_stat_wal_receiver
                       WHERE status = 'streaming'
                   )
                   AND EXISTS (
                       SELECT 1 FROM pg36_ch33_lineage
                       WHERE marker = 'after-divergence'
                   )
                """,
                timeout=45,
            )
            rewind_target = facts(binaries["psql"], sa, args.source_port)
            transitions.append({"event": "A-rewound-and-streaming", "at": now()})
            stop(binaries["pg_ctl"], a)
            running.remove("A")

            _, base_c_metric = execute(
                [
                    binaries["pg_basebackup"],
                    "-h",
                    sb,
                    "-p",
                    str(args.rewind_port),
                    "-U",
                    "postgres",
                    "-D",
                    c,
                    "-X",
                    "stream",
                    "-R",
                    "--checkpoint=fast",
                    "--no-password",
                ],
                timeout=120,
            )
            if not (c / "standby.signal").exists():
                raise ExerciseError("fresh base backup did not create standby.signal")
            start(binaries["pg_ctl"], c, sc, args.basebackup_port)
            running.add("C")
            wait_sql(
                binaries["psql"],
                sc,
                args.basebackup_port,
                """
                SELECT pg_is_in_recovery()
                   AND EXISTS (
                       SELECT 1 FROM pg_stat_wal_receiver
                       WHERE status = 'streaming'
                   )
                   AND EXISTS (
                       SELECT 1 FROM pg36_ch33_lineage
                       WHERE marker = 'after-divergence'
                   )
                """,
                timeout=45,
            )
            basebackup_target = facts(
                binaries["psql"], sc, args.basebackup_port
            )
            transitions.append({"event": "C-basebackup-and-streaming", "at": now()})

            result.update({
                "postgresql_version": sql(
                    binaries["psql"],
                    sb,
                    args.rewind_port,
                    "SHOW server_version",
                ),
                "initdb": init_metric,
                "initial_basebackup": base_b_metric,
                "a_base": a_base,
                "b_promoted": b_promoted,
                "a_divergent": a_divergent,
                "rewind": rewind_metric,
                "rewind_target": rewind_target,
                "fresh_basebackup": base_c_metric,
                "basebackup_target": basebackup_target,
                "same_system_identifier": len({
                    a_base["system_identifier"],
                    b_promoted["system_identifier"],
                    a_divergent["system_identifier"],
                    rewind_target["system_identifier"],
                    basebackup_target["system_identifier"],
                }) == 1,
                "timeline_diverged": (
                    int(b_promoted["timeline"]) > int(a_divergent["timeline"])
                ),
                "rewind_target_has_new_primary": (
                    "new-primary" in rewind_target["markers"]
                    and "after-divergence" in rewind_target["markers"]
                ),
                "rewind_target_has_old_divergent": (
                    "old-primary-divergent" in rewind_target["markers"]
                ),
                "basebackup_target_streaming": (
                    basebackup_target["in_recovery"] is True
                    and basebackup_target["receiver_status"] == "streaming"
                ),
                "completed_at": now(),
            })
        finally:
            for name, data_dir in (("A", a), ("C", c), ("B", b)):
                try:
                    stop(binaries["pg_ctl"], data_dir)
                except Exception:
                    pass
                running.discard(name)
            marker = root / ".pg36-ch33-owned"
            if (
                root.exists()
                and marker.is_file()
                and marker.read_text().strip() == args.run_id
                and root.name == prefix.name + "-" + args.run_id
            ):
                shutil.rmtree(root)
            result["cleanup"] = {
                "running_instances_after": sorted(running),
                "root_exists_after": root.exists(),
                "exact_marker_matched": not root.exists(),
            }
        print(json.dumps(result, sort_keys=True))

    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "pg36-ch33-rebuild-error-v1",
                    "error_class": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise
    '''
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        contract = requirements["rebuild_lab"]
        if (
            not isinstance(args.run_id, str)
            or len(args.run_id) != 36
            or any(
                character not in "0123456789abcdef-"
                for character in args.run_id
            )
        ):
            raise LabError("run identity is not a canonical lowercase UUID")
        root = f"{contract['root_prefix']}-{args.run_id}"
        if root != f"/tmp/pg36-ch33-rebuild-{args.run_id}":
            raise LabError("rebuild root drifted from the exact contract")
        result = run(
            ssh_base(args.ssh_user, str(contract["address"]))
            + [
                "sudo",
                "-n",
                "-iu",
                "postgres",
                "python3",
                "-",
                "--root",
                root,
                "--run-id",
                args.run_id,
                "--source-port",
                str(contract["source_port"]),
                "--rewind-port",
                str(contract["rewind_target_port"]),
                "--basebackup-port",
                str(contract["basebackup_target_port"]),
            ],
            stdin=REMOTE_EXERCISE,
            timeout=360,
        )
        value: Any = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise LabError("remote rebuild lab returned no object")
        write_json(args.output, value)
    except (
        KeyError,
        TypeError,
        OSError,
        json.JSONDecodeError,
        LabError,
    ) as exc:
        print(f"rebuild lab failed: {exc}", file=sys.stderr)
        return 1
    print("status=rebuild-lab-ok")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
