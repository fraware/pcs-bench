#!/usr/bin/env python3
"""Inline metric_summary in BenchmarkReport.v0 (delegates to pcs_bench.schema_sync)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcs_bench.schema_sync import ensure_benchmark_report_metric_summary_inline


def main() -> int:
    root = ROOT
    targets = [
        root.parent / "pcs-core" / "schemas" / "BenchmarkReport.v0.schema.json",
        root / "src" / "pcs_bench" / "schemas" / "json" / "BenchmarkReport.v0.json",
    ]
    patched = 0
    for path in targets:
        if ensure_benchmark_report_metric_summary_inline(path):
            print(f"patched {path}")
            patched += 1
    if not patched:
        print("no legacy MetricSummary refs found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
