#!/usr/bin/env python3
"""Consume stdin slowly to create controlled PostgreSQL socket backpressure."""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-bytes", type=int, default=4096)
    parser.add_argument("--delay-ms", type=int, default=100)
    args = parser.parse_args()

    if not 1024 <= args.chunk_bytes <= 65536:
        parser.error("chunk-bytes must be in 1024..65536")
    if not 10 <= args.delay_ms <= 1000:
        parser.error("delay-ms must be in 10..1000")

    consumed = 0
    while True:
        chunk = sys.stdin.buffer.read(args.chunk_bytes)
        if not chunk:
            break
        consumed += len(chunk)
        time.sleep(args.delay_ms / 1000)

    print(f"consumed_bytes={consumed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
