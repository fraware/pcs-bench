"""Unit tests for reports and baselines."""

from pathlib import Path

from pcs_bench.baselines import compare_reports
from pcs_bench.reports import load_report, save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary, RepoCommits


def test_save_and_load_report(tmp_path):
    report = BenchmarkReport(
        benchmark_suite_id="test",
        repo_commits=RepoCommits(pcs_bench="abc123"),
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
        metrics=["release_reproducibility_score"],
        metric_summaries=[],
    )
    path = tmp_path / "report.json"
    save_report(report, path)
    loaded = load_report(path)
    assert loaded.report_id == report.report_id
    assert loaded.signature_or_digest is not None


def test_compare_detects_regression():
    old = BenchmarkReport(
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=0.94, applicability="measured")
        ]
    )
    new = BenchmarkReport(
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=0.88, applicability="measured")
        ]
    )
    cmp = compare_reports(old, new)
    regressions = cmp.regressions()
    assert len(regressions) == 1
    assert regressions[0].name == "failure_localization_accuracy"
