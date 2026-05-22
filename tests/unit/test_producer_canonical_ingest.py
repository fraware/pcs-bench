"""Tests for release-grade canonical ingest reuse in producer gate."""

from __future__ import annotations

import shutil
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.producer_contracts import contract_for
from pcs_bench.producer_gate import (
    _canonical_ingest_release_ready,
    collect_producer_ingests,
)
from pcs_bench.producer_fixtures import resolve_schema_root

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"
_PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"


def _pcs_core() -> Path:
    candidate = Path(__file__).resolve().parents[3] / "pcs-core"
    if (candidate / "schemas").is_dir():
        return candidate
    return _PKG_ROOT


def test_canonical_ingest_release_ready_accepts_valid_fixture(
    tmp_path: Path, monkeypatch
) -> None:
    contract = contract_for("certifyedge")
    assert contract is not None
    repo = tmp_path / "ce"
    src = FIXTURE_ROOT / "certifyedge" / "pcs_bench_ingest.v0.json"
    dest = repo / contract.ingest_rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    schema_root = resolve_schema_root(_pcs_core())
    monkeypatch.setattr(
        "pcs_bench.producer_gate.validate_ingest_json",
        lambda *_a, **_k: [],
    )
    ready = _canonical_ingest_release_ready(
        repo, contract, schema_root=schema_root, release_grade=True
    )
    assert ready == dest.resolve()


def test_collect_skips_benchmark_when_canonical_ingest_ready(tmp_path: Path, monkeypatch) -> None:
    from pcs_bench.producer_gate import PRODUCER_BENCHMARKS

    _REPO_FIXTURE_DIR = {
        "certifyedge": "certifyedge",
        "provability-fabric": "provability_fabric",
        "scientific-memory": "scientific_memory",
        "labtrust-gym": "labtrust",
    }
    cfg = BenchConfig()
    cfg.repos.pcs_core = _pcs_core()
    for spec in PRODUCER_BENCHMARKS:
        fixture_dir = _REPO_FIXTURE_DIR[spec.producer]
        repo = tmp_path / spec.producer
        contract = contract_for(spec.producer)
        assert contract is not None
        src = FIXTURE_ROOT / fixture_dir / "pcs_bench_ingest.v0.json"
        dest = repo / contract.ingest_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if spec.producer == "certifyedge":
            cfg.repos.certifyedge = repo
        elif spec.producer == "provability-fabric":
            cfg.repos.provability_fabric = repo
        elif spec.producer == "scientific-memory":
            cfg.repos.scientific_memory = repo
        elif spec.producer == "labtrust-gym":
            cfg.repos.labtrust = repo

    calls: list[str] = []

    def _track_benchmark(cfg, spec, *, scratch_dir):
        calls.append(spec.producer)
        from pcs_bench.producer_gate import ProducerBenchmarkRunOutcome

        return ProducerBenchmarkRunOutcome()

    def _no_validate(*_a, **_k):
        return []

    monkeypatch.setattr("pcs_bench.producer_gate.validate_ingest_json", _no_validate)
    monkeypatch.setattr("pcs_bench.producer_ingest.validate_ingest_data_strict", _no_validate)
    monkeypatch.setattr(
        "pcs_bench.producer_gate.run_producer_benchmark",
        _track_benchmark,
    )

    result = collect_producer_ingests(
        cfg,
        scratch_dir=tmp_path / "scratch",
        run_benchmarks=True,
        release_grade=True,
        refresh_producer_ingests=False,
    )
    assert calls == [], calls
    assert len(result.reports) == len(PRODUCER_BENCHMARKS)
