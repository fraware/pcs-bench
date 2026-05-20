"""Strict BenchmarkReport.v0 schema validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pcs_bench.report_export import to_benchmark_report_v0_dict
from pcs_bench.reports import report_digest, save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary, RepoCommits
from pcs_bench.validation import validate_report_data_strict


def _minimal_report(**overrides) -> dict:
    report = BenchmarkReport(
        benchmark_suite_id="test-suite",
        repo_commits=RepoCommits(pcs_bench="abc123"),
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="case-valid",
                suite_id="test-suite",
                expected_status="Admitted",
                observed_status="Admitted",
                passed=True,
            ),
            BenchmarkRun(
                run_id="r2",
                case_id="case-invalid",
                suite_id="test-suite",
                expected_status="Rejected",
                observed_status="Rejected",
                expected_failure_code="x",
                observed_failure_code="x",
                passed=True,
            ),
        ],
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=1.0, applicability="measured"),
        ],
        summary={"total_runs": 2, "passed": 2, "failed": 0},
        coverage={"cases": 2},
        failures=[],
    )
    report.metric_summaries = [
        MetricSummary(name="release_reproducibility_score", score=1.0, applicability="measured"),
        MetricSummary(name="failure_localization_accuracy", score=1.0, applicability="measured"),
        MetricSummary(name="certificate_completeness_score", score=1.0, applicability="measured"),
        MetricSummary(name="registry_coverage_score", score=1.0, applicability="measured"),
        MetricSummary(name="formal_check_coverage_score", score=0.5, applicability="measured"),
        MetricSummary(
            name="scientific_memory_interpretability_score",
            score=0.5,
            applicability="insufficient_cases",
            reason="No memory cases",
        ),
        MetricSummary(name="repair_hint_quality_score", score=1.0, applicability="measured"),
        MetricSummary(name="cross_domain_portability_score", score=0.8, applicability="measured"),
    ]
    report.metrics = {s.name: s.score for s in report.metric_summaries if s.score is not None}
    report.finalize(digest=report_digest(report))
    data = to_benchmark_report_v0_dict(report)
    data.update(overrides)
    return data


def test_benchmark_report_validates_against_pcs_core_schema(tmp_path: Path) -> None:
    data = _minimal_report()
    pcs_core = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"
    errors = validate_report_data_strict(data, pcs_core)
    assert errors == [], errors


def test_report_rejects_missing_source_commit() -> None:
    data = _minimal_report()
    del data["source_commit"]
    pcs_core = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"
    errors = validate_report_data_strict(data, pcs_core)
    assert any("source_commit" in e for e in errors)


def test_report_rejects_invalid_metric_shape() -> None:
    data = _minimal_report()
    data["metrics"] = ["not", "an", "object"]
    pcs_core = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"
    errors = validate_report_data_strict(data, pcs_core)
    assert any("metrics" in e for e in errors)


def test_report_rejects_missing_signature_or_digest() -> None:
    data = _minimal_report()
    del data["signature_or_digest"]
    pcs_core = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"
    errors = validate_report_data_strict(data, pcs_core)
    assert any("signature_or_digest" in e for e in errors)


def test_save_report_emits_valid_json(tmp_path: Path) -> None:
    report = BenchmarkReport(
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="c1",
                suite_id="s1",
                expected_status="Admitted",
                observed_status="Admitted",
                passed=True,
            )
        ],
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=1.0),
        ],
        summary={},
        coverage={},
    )
    path = tmp_path / "report.json"
    save_report(report, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source_repo"]
    assert data["source_commit"]
    assert data["signature_or_digest"].startswith("sha256:")
