#!/usr/bin/env python3
"""Copy pcs-core golden PcsBenchIngest examples into pcs-bench test fixtures."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "producer_ingest"

MAPPING = {
    "certifyedge.pcs_bench_ingest.valid.json": "certifyedge",
    "provability_fabric.pcs_bench_ingest.valid.json": "provability_fabric",
    "scientific_memory.pcs_bench_ingest.valid.json": "scientific_memory",
    "labtrust.pcs_bench_ingest.valid.json": "labtrust",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="pcs-core repository root",
    )
    args = parser.parse_args()
    ingest_dir = args.pcs_core / "examples" / "benchmark_ingest"
    if not ingest_dir.is_dir():
        print(f"ERROR: {ingest_dir} not found", file=sys.stderr)
        return 1

    for source_name, dest_dir in MAPPING.items():
        source = ingest_dir / source_name
        if not source.is_file():
            print(f"MISSING {source}", file=sys.stderr)
            return 1
        dest_parent = FIXTURE_ROOT / dest_dir
        dest_parent.mkdir(parents=True, exist_ok=True)
        dest = dest_parent / "pcs_bench_ingest.v0.json"
        shutil.copy2(source, dest)
        print(f"Copied {source_name} -> {dest.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
