#!/usr/bin/env python3
"""Validate all producer PcsBenchIngest.v0 fixtures under tests/fixtures/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcs_bench.producer_fixtures import validate_all_producer_fixtures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="pcs-core checkout for schemas (falls back to embedded schemas)",
    )
    parser.add_argument(
        "--release-grade",
        action="store_true",
        help="Require release-grade semantic adequacy on golden fixtures.",
    )
    args = parser.parse_args()
    pcs_core = args.pcs_core if args.pcs_core.is_dir() else None

    failed = False
    for result in validate_all_producer_fixtures(
        pcs_core, release_grade=args.release_grade
    ):
        if result.valid:
            print(f"OK {result.producer} {result.path}")
        else:
            failed = True
            print(f"FAIL {result.producer} {result.path}", file=sys.stderr)
            for err in result.errors:
                print(f"  - {err}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
