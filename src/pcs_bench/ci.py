"""CI mode threshold enforcement."""

from __future__ import annotations

from pcs_bench.config import BenchConfig
from pcs_bench.errors import ThresholdViolationError
from pcs_bench.schemas import BenchmarkReport, MetricSummary


def check_ci_thresholds(
    report: BenchmarkReport,
    config: BenchConfig,
    *,
    required_metrics: set[str] | None = None,
) -> list[ThresholdViolationError]:
    violations: list[ThresholdViolationError] = []
    threshold_map = config.thresholds.model_dump()
    summaries_by_name = {s.name: s for s in report.metric_summaries}

    for metric_name, threshold in threshold_map.items():
        summary = summaries_by_name.get(metric_name)
        if summary:
            if summary.applicability != "measured" or summary.score is None:
                if required_metrics and metric_name in required_metrics:
                    violations.append(
                        ThresholdViolationError(
                            metric_name,
                            -1.0,
                            threshold,
                            [],
                            message=(
                                f"Required metric {metric_name} was not measured "
                                f"({summary.applicability}: {summary.reason})"
                            ),
                        )
                    )
                continue
            score = summary.score
        else:
            score = report.metrics.get(metric_name)
            if score is None:
                continue

        if score < threshold:
            failed_cases = _failed_cases_for_metric(report, metric_name)
            violations.append(
                ThresholdViolationError(metric_name, score, threshold, failed_cases)
            )

    for run in report.runs:
        if run.expected_status in ("Admitted", "Accepted") and not run.passed:
            violations.append(
                ThresholdViolationError("valid_release_rejected", 0.0, 1.0, [run.case_id])
            )

    for run in report.runs:
        if run.expected_status == "Rejected" and run.observed_status in ("Admitted", "Accepted"):
            violations.append(
                ThresholdViolationError("invalid_release_accepted", 0.0, 1.0, [run.case_id])
            )

    return violations


def check_live_required(
    report: BenchmarkReport,
    live_required_suites: list[str],
) -> list[str]:
    """Return error messages when live-required suites ran only simulated cases."""
    errors: list[str] = []
    mode = report.summary.get("execution_mode", "simulate")
    if mode == "live":
        return errors
    live_cases = int(report.summary.get("live_cases", 0))
    if live_required_suites and live_cases == 0:
        errors.append(
            f"CI live gate failed: suites {live_required_suites} require live execution "
            f"but execution_mode={mode!r} with live_cases=0"
        )
    for suite_id in live_required_suites:
        suite_runs = [r for r in report.runs if r.suite_id == suite_id]
        if suite_runs and live_cases == 0:
            errors.append(
                f"Suite {suite_id} is marked live_required_for_release but no cases ran live"
            )
    return errors


def format_ci_failure(violations: list[ThresholdViolationError]) -> str:
    lines: list[str] = []
    for v in violations:
        if v.message and "not measured" in v.message:
            lines.append(f"FAILED: {v.message}")
        else:
            lines.append(f"FAILED: {v.metric} below threshold")
            lines.append(f"score: {v.score:.2f}")
            lines.append(f"threshold: {v.threshold:.2f}")
        if v.failed_cases:
            lines.append("failed cases:")
            for c in v.failed_cases:
                lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines).strip()
