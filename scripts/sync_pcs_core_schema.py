#!/usr/bin/env python3
"""Copy BenchmarkReport.v0 and related schemas from a local pcs-core checkout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcs_bench.schema_sync import sync_schemas_from_pcs_core


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="Path to pcs-core repository",
    )
    args = parser.parse_args()
    result = sync_schemas_from_pcs_core(args.pcs_core)
    if result.errors:
        for err in result.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    for name in result.copied:
        print(f"Copied {name}.json")
    if result.missing:
        print("Not found in pcs-core (using embedded fallback):", ", ".join(result.missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
