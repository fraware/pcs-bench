"""Tests for producer benchmark run diagnostics."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.producer_gate import PRODUCER_BENCHMARKS, run_producer_benchmark


def test_run_producer_benchmark_errors_when_cases_missing(tmp_path: Path) -> None:
    cfg = BenchConfig()
    cfg.repos.certifyedge = tmp_path / "certifyedge"
    cfg.repos.certifyedge.mkdir()
    spec = next(s for s in PRODUCER_BENCHMARKS if s.producer == "certifyedge")
    outcome = run_producer_benchmark(cfg, spec, scratch_dir=tmp_path / "scratch")
    assert outcome.ingest_path is None
    assert outcome.errors
    assert "no benchmark cases directory" in outcome.errors[0]
