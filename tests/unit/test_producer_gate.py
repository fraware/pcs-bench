"""Tests for producer gate aggregation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.producer_gate import (
    PRODUCER_BENCHMARKS,
    aggregate_gate_report,
    collect_producer_ingests,
)
from pcs_bench.reports import load_report, save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"

_REPO_FIXTURE_DIR = {
    "certifyedge": "certifyedge",
    "provability-fabric": "provability_fabric",
    "scientific-memory": "scientific_memory",
    "labtrust-gym": "labtrust",
}


def _setup_producer_repos(tmp_path: Path) -> BenchConfig:
    cfg = BenchConfig()
    for spec in PRODUCER_BENCHMARKS:
        fixture_dir = _REPO_FIXTURE_DIR[spec.producer]
        repo = tmp_path / spec.producer
        src = FIXTURE_ROOT / fixture_dir / "pcs_bench_ingest.v0.json"
        dest = repo / spec.ingest_rel_path
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
    return cfg


def _bench_only_report(tmp_path: Path) -> Path:
    report = BenchmarkReport(
        benchmark_suite_id="cross_domain",
        runs=[
            BenchmarkRun(
                run_id="x1",
                case_id="cross-domain-tool-use-v0",
                suite_id="cross_domain",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            )
        ],
        summary={"execution_mode": "simulate", "evidence_grade": "developer"},
    )
    path = tmp_path / "bench.json"
    save_report(report, path)
    return path


def test_aggregate_gate_report_from_fixtures(tmp_path: Path) -> None:
    cfg = _setup_producer_repos(tmp_path)
    bench_path = _bench_only_report(tmp_path)
    out = tmp_path / "aggregate.json"

    errors = aggregate_gate_report(
        cfg,
        bench_path,
        scratch_dir=tmp_path / "scratch",
        run_producer_benchmarks=False,
        out_path=out,
        require_all_producers=True,
    )
    assert errors == [], errors

    merged = load_report(out)
    assert len(merged.runs) >= 2
    assert (
        merged.coverage.get("certificate_completeness")
        or merged.coverage.get("explain_quality")
        or merged.coverage.get("registry")
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "metrics" in payload
    assert payload["benchmark_suite_id"] == "all"

    manifest_path = tmp_path / "producer_merge_manifest.v0.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["producer_reports"]) == len(PRODUCER_BENCHMARKS)
    assert manifest["producer_reports"][0]["ingest_digest"].startswith("sha256:")


def test_aggregate_gate_report_marks_fixture_fallback(tmp_path: Path) -> None:
    cfg = BenchConfig(
        repos={
            "pcs_core": tmp_path / "no-pcs-core",
            "labtrust": tmp_path / "no-labtrust",
            "certifyedge": tmp_path / "no-certifyedge",
            "provability_fabric": tmp_path / "no-pf",
            "scientific_memory": tmp_path / "no-sm",
        }
    )
    bench_path = _bench_only_report(tmp_path)
    out = tmp_path / "aggregate.json"
    errors = aggregate_gate_report(
        cfg,
        bench_path,
        scratch_dir=tmp_path / "scratch",
        run_producer_benchmarks=False,
        out_path=out,
        use_fixture_fallback=True,
    )
    assert errors == []
    merged = load_report(out)
    assert merged.summary.get("fixture_fallback_used") is True
    assert merged.summary.get("evidence_grade") == "developer"


def test_collect_producer_ingests_fixture_fallback(tmp_path: Path) -> None:
    cfg = BenchConfig(
        repos={
            "pcs_core": tmp_path / "no-pcs-core",
            "labtrust": tmp_path / "no-labtrust",
            "certifyedge": tmp_path / "no-certifyedge",
            "provability_fabric": tmp_path / "no-pf",
            "scientific_memory": tmp_path / "no-sm",
        }
    )
    result = collect_producer_ingests(
        cfg,
        scratch_dir=tmp_path / "scratch",
        run_benchmarks=False,
        use_fixture_fallback=True,
    )
    assert not result.errors
    assert len(result.reports) == len(PRODUCER_BENCHMARKS)
