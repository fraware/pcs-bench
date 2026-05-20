"""Strict BenchmarkReport.v0 schema validation tests."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.report_export import to_benchmark_report_v0_dict
from pcs_bench.reports import report_digest, save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary, RepoCommits
from pcs_bench.validation import validate_report_data_strict


def _pcs_core() -> Path:
    root = Path(__file__).resolve().parents[2]
    candidate = root.parent / "pcs-core"
    if (candidate / "schemas").is_dir():
        return candidate
    return root / "src" / "pcs_bench"


def _minimal_report(tmp_path: Path, **overrides) -> dict:
    report = BenchmarkReport(
        benchmark_suite_id="test-suite",
        repo_commits=RepoCommits(pcs_bench="abc123"),
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="case-valid",
                suite_id="test-suite",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            ),
            BenchmarkRun(
                run_id="r2",
                case_id="case-invalid",
                suite_id="test-suite",
                expected_status="failed",
                expected_system_outcome="rejected",
                observed_status="failed",
                observed_system_outcome="rejected",
                expected_failure_code="trace_hash_mismatch",
                observed_failure_code="trace_hash_mismatch",
                expected_responsible_component="runtime_producer",
                observed_responsible_component="runtime_producer",
                passed=True,
            ),
        ],
        metric_summaries=[
            MetricSummary(name="release_reproducibility_score", score=1.0, applicability="measured"),
            MetricSummary(name="failure_localization_accuracy", score=1.0, applicability="measured"),
            MetricSummary(name="certificate_completeness_score", score=1.0, applicability="measured"),
            MetricSummary(name="registry_coverage_score", score=1.0, applicability="measured"),
            MetricSummary(name="formal_check_coverage_score", score=0.5, applicability="measured"),
            MetricSummary(
                name="scientific_memory_interpretability_score",
                score=None,
                applicability="insufficient_cases",
                reason="No memory cases",
            ),
            MetricSummary(name="repair_hint_quality_score", score=1.0, applicability="measured"),
            MetricSummary(name="cross_domain_portability_score", score=0.8, applicability="measured"),
        ],
        summary={
            "total_cases": 2,
            "passed_cases": 2,
            "failed_cases": 0,
            "expected_failures_detected": 1,
            "unexpected_passes": 0,
            "unexpected_failures": 0,
            "failure_localization_accuracy": 1.0,
            "repair_hint_accuracy": 1.0,
            "formal_check_coverage": 0.5,
            "registry_coverage": 1.0,
            "scientific_memory_render_coverage": 0.0,
            "execution_mode": "simulate",
            "evidence_grade": "developer",
            "live_cases": 0,
            "simulated_cases": 2,
            "hybrid_fallback_cases": 0,
        },
        coverage={},
        failures=[],
    )
    report.finalize(digest=report_digest(report))
    data = to_benchmark_report_v0_dict(report, runs_output_dir=tmp_path / "runs")
    data.update(overrides)
    return data


def test_benchmark_report_validates_against_pcs_core_schema(tmp_path: Path) -> None:
    data = _minimal_report(tmp_path)
    errors = validate_report_data_strict(data, _pcs_core())
    assert errors == [], errors


def test_report_rejects_missing_source_commit(tmp_path: Path) -> None:
    data = _minimal_report(tmp_path)
    del data["source_commit"]
    errors = validate_report_data_strict(data, _pcs_core())
    assert any("source_commit" in e for e in errors)


def test_report_rejects_invalid_metric_shape(tmp_path: Path) -> None:
    data = _minimal_report(tmp_path)
    data["metrics"] = [123]
    errors = validate_report_data_strict(data, _pcs_core())
    assert errors


def test_report_rejects_missing_signature_or_digest(tmp_path: Path) -> None:
    data = _minimal_report(tmp_path)
    del data["signature_or_digest"]
    errors = validate_report_data_strict(data, _pcs_core())
    assert any("signature_or_digest" in e for e in errors)


def test_save_report_emits_valid_json(tmp_path: Path) -> None:
    report = BenchmarkReport(
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="c1",
                suite_id="s1",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            )
        ],
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=1.0),
        ],
        summary={"execution_mode": "simulate", "evidence_grade": "developer"},
        coverage={},
    )
    path = tmp_path / "report.json"
    save_report(report, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data["metrics"], list)
    assert data["source_repo"]
    assert len(data["source_commit"]) == 40
    assert data["signature_or_digest"].startswith("sha256:")
