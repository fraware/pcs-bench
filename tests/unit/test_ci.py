"""Tests for CI threshold and per-case policy enforcement."""

from pcs_bench.ci import check_ci_thresholds
from pcs_bench.config import BenchConfig
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary


def test_ci_flags_missed_invalid_release():
    report = BenchmarkReport(
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="labtrust-trace-hash-tamper-v0",
                suite_id="labtrust-qc-release-v0",
                expected_status="failed",
                expected_system_outcome="rejected",
                expected_failure_code="trace_hash_mismatch",
                observed_status="failed",
                observed_system_outcome="rejected",
                observed_failure_code="wrong_code",
                passed=False,
            ),
        ],
        metric_summaries=[
            MetricSummary(
                name="failure_localization_accuracy",
                score=1.0,
                applicability="measured",
            ),
        ],
    )
    violations = check_ci_thresholds(report, BenchConfig())
    assert any(v.metric == "invalid_release_not_detected" for v in violations)


def test_ci_passes_when_invalid_release_detected():
    report = BenchmarkReport(
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="labtrust-trace-hash-tamper-v0",
                suite_id="labtrust-qc-release-v0",
                expected_status="failed",
                expected_system_outcome="rejected",
                expected_failure_code="trace_hash_mismatch",
                observed_status="failed",
                observed_system_outcome="rejected",
                observed_failure_code="trace_hash_mismatch",
                observed_responsible_component="runtime_producer",
                expected_responsible_component="runtime_producer",
                passed=True,
            ),
        ],
        metric_summaries=[
            MetricSummary(
                name="failure_localization_accuracy",
                score=1.0,
                applicability="measured",
            ),
        ],
    )
    violations = check_ci_thresholds(report, BenchConfig())
    assert not any(v.metric == "invalid_release_not_detected" for v in violations)
