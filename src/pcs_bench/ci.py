"""CI mode threshold enforcement."""

from __future__ import annotations

from pcs_bench.benchmark_vocabulary import (
    is_invalid_release_case,
    is_valid_release_case,
)
from pcs_bench.config import BenchConfig
from pcs_bench.errors import ThresholdViolationError
from pcs_bench.schemas import BenchmarkReport


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
            continue

        if score < threshold:
            failed_cases = _failed_cases_for_metric(report, metric_name)
            violations.append(
                ThresholdViolationError(metric_name, score, threshold, failed_cases)
            )

    for run in report.runs:
        if is_valid_release_case(run.expected_status, run.expected_system_outcome) and not run.passed:
            violations.append(
                ThresholdViolationError("valid_release_rejected", 0.0, 1.0, [run.case_id])
            )

    for run in report.runs:
        if is_invalid_release_case(run.expected_status, run.expected_system_outcome) and not run.passed:
            violations.append(
                ThresholdViolationError("invalid_release_not_detected", 0.0, 1.0, [run.case_id])
            )

    return violations


def check_live_required(
    report: BenchmarkReport,
    live_required_suites: list[str],
    *,
    release_grade: bool = False,
) -> list[str]:
    errors: list[str] = []
    mode = report.summary.get("execution_mode", "simulate")
    live_cases = int(report.summary.get("live_cases", 0))
    hybrid_fb = int(report.summary.get("hybrid_fallback_cases", 0))

    if release_grade or report.summary.get("evidence_grade") == "release":
        if mode != "live":
            errors.append(f"Release-grade report requires execution_mode=live, got {mode!r}")
        if live_cases == 0:
            errors.append("Release-grade report requires live_cases > 0")
        if hybrid_fb > 0:
            errors.append("Release-grade report cannot include hybrid_fallback_cases")

    for suite_id in live_required_suites:
        suite_runs = [r for r in report.runs if r.suite_id == suite_id]
        if not suite_runs:
            continue
        if release_grade or report.summary.get("evidence_grade") == "release":
            if any(r.execution_kind == "hybrid_fallback" for r in suite_runs):
                errors.append(
                    f"Suite {suite_id} is live_required_for_release but used hybrid simulation fallback"
                )
            if not any(r.execution_kind == "live" for r in suite_runs):
                errors.append(
                    f"Suite {suite_id} is live_required_for_release but no cases ran live"
                )
        elif live_cases == 0:
            errors.append(
                f"Suite {suite_id} is marked live_required_for_release but no cases ran live"
            )
    return errors


def check_repo_commits_resolved(report: BenchmarkReport) -> list[str]:
    """Fail live/release runs when sibling repo commits could not be resolved."""
    errors: list[str] = []
    for name, commit in report.repo_commits.model_dump().items():
        if commit in ("unknown", "placeholder", "local") or len(str(commit)) != 40:
            errors.append(
                f"Could not resolve 40-char git commit for {name} (got {commit!r})"
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


def _failed_cases_for_metric(report: BenchmarkReport, metric_name: str) -> list[str]:
    if metric_name == "failure_localization_accuracy":
        return [
            r.case_id
            for r in report.runs
            if is_invalid_release_case(r.expected_status, r.expected_system_outcome)
            and r.observed_responsible_component != r.expected_responsible_component
        ]
    if metric_name == "release_reproducibility_score":
        return [
            r.case_id
            for r in report.runs
            if is_valid_release_case(r.expected_status, r.expected_system_outcome) and not r.passed
        ]
    return [f.case_id for f in report.failures]
