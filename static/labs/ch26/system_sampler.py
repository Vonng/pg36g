#!/usr/bin/env python3
"""Emit secret-free Linux resource samples as JSON lines."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=0.25)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_cpu() -> dict[str, int]:
    first = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    fields = first.split()
    names = [
        "user",
        "nice",
        "system",
        "idle",
        "iowait",
        "irq",
        "softirq",
        "steal",
        "guest",
        "guest_nice",
    ]
    values = [int(value) for value in fields[1:]]
    return dict(zip(names, values, strict=False))


def read_mem() -> dict[str, int]:
    wanted = {
        "MemTotal",
        "MemAvailable",
        "Buffers",
        "Cached",
        "SwapTotal",
        "SwapFree",
        "Dirty",
        "Writeback",
    }
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, rest = line.partition(":")
        if key not in wanted:
            continue
        value = int(rest.strip().split()[0]) * 1024
        result[key] = value
    return result


def root_device() -> tuple[int, int]:
    stat = os.stat("/")
    return os.major(stat.st_dev), os.minor(stat.st_dev)


def read_disk(major: int, minor: int) -> dict[str, int] | None:
    for line in Path("/proc/diskstats").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if int(fields[0]) != major or int(fields[1]) != minor:
            continue
        return {
            "reads_completed": int(fields[3]),
            "sectors_read": int(fields[5]),
            "read_ms": int(fields[6]),
            "writes_completed": int(fields[7]),
            "sectors_written": int(fields[9]),
            "write_ms": int(fields[10]),
            "io_in_progress": int(fields[11]),
            "io_ms": int(fields[12]),
            "weighted_io_ms": int(fields[13]),
        }
    return None


def sample(major: int, minor: int) -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    return {
        "captured_at": utc_now(),
        "monotonic_seconds": time.monotonic(),
        "cpu": read_cpu(),
        "memory_bytes": read_mem(),
        "load": {
            "one": load1,
            "five": load5,
            "fifteen": load15,
        },
        "root_device": {
            "major": major,
            "minor": minor,
            "counters": read_disk(major, minor),
        },
    }


def main() -> int:
    args = parse_args()
    if args.duration <= 0 or args.interval < 0.05:
        raise SystemExit("duration must be positive and interval at least 0.05")
    major, minor = root_device()
    deadline = time.monotonic() + args.duration
    while True:
        print(json.dumps(sample(major, minor), separators=(",", ":")), flush=True)
        now = time.monotonic()
        if now >= deadline:
            break
        time.sleep(min(args.interval, max(0.0, deadline - now)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
