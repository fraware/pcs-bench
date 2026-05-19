"""CI mode threshold enforcement."""

from __future__ import annotations

from pcs_bench.config import BenchConfig
from pcs_bench.errors import ThresholdViolationError
from pcs_bench.schemas import BenchmarkReport


def check_ci_thresholds(report: BenchmarkReport, config: BenchConfig) -> list[ThresholdViolationError]:
    violations: list[ThresholdViolationError] = []

    threshold_map = config.thresholds.model_dump()

    for metric_name, threshold in threshold_map.items():
        score = report.metrics.get(metric_name)
        if score is None:
            continue
        if score < threshold:
            failed_cases = _failed_cases_for_metric(report, metric_name)
            violations.append(
                ThresholdViolationError(metric_name, score, threshold, failed_cases)
            )

    # Valid release rejected
    for run in report.runs:
        if run.expected_status in ("Admitted", "Accepted") and not run.passed:
            violations.append(
                ThresholdViolationError(
                    "valid_release_rejected",
                    0.0,
                    1.0,
                    [run.case_id],
                )
            )

    # Invalid release accepted
    for run in report.runs:
        if run.expected_status == "Rejected" and run.observed_status in ("Admitted", "Accepted"):
            violations.append(
                ThresholdViolationError(
                    "invalid_release_accepted",
                    0.0,
                    1.0,
                    [run.case_id],
                )
            )

    return violations


def _failed_cases_for_metric(report: BenchmarkReport, metric_name: str) -> list[str]:
    if metric_name == "failure_localization_accuracy":
        return [
            r.case_id
            for r in report.runs
            if r.expected_status == "Rejected"
            and r.observed_responsible_component != r.expected_responsible_component
        ]
    if metric_name == "release_reproducibility_score":
        return [
            r.case_id
            for r in report.runs
            if r.expected_status in ("Admitted", "Accepted") and not r.passed
        ]
    return [f.case_id for f in report.failures]


def format_ci_failure(violations: list[ThresholdViolationError]) -> str:
    lines: list[str] = []
    for v in violations:
        lines.append(f"FAILED: {v.metric} below threshold")
        lines.append(f"score: {v.score:.2f}")
        lines.append(f"threshold: {v.threshold:.2f}")
        if v.failed_cases:
            lines.append("failed cases:")
            for c in v.failed_cases:
                lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines).strip()
