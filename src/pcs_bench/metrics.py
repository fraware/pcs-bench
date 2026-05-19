"""Core benchmark metrics computation."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.metrics_definitions import (
    CERTIFICATE_REQUIRED_FIELDS,
    REQUIRED_MEMORY_SECTIONS,
)
from pcs_bench.schemas import BenchmarkRun, MetricSummary

# Re-export for backward compatibility
__all__ = [
    "CERTIFICATE_REQUIRED_FIELDS",
    "REQUIRED_MEMORY_SECTIONS",
    "compute_all_metrics",
    "apply_metrics_to_report",
    "METRIC_COMPUTERS",
]


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _load_run_analysis(run: BenchmarkRun) -> dict:
    paths: list[Path] = []
    if run.artifact_analysis_path:
        paths.append(Path(run.artifact_analysis_path))
    paths.extend(Path(a) for a in run.artifacts if a.endswith("artifact_analysis.json"))
    for path in paths:
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def compute_release_reproducibility_score(runs: list[BenchmarkRun]) -> MetricSummary:
    valid = [r for r in runs if r.expected_status in ("Admitted", "Accepted")]
    reproducible = [r for r in valid if r.passed and r.observed_status in ("Admitted", "Accepted")]
    return MetricSummary(
        name="release_reproducibility_score",
        score=_safe_ratio(len(reproducible), len(valid)),
        numerator=len(reproducible),
        denominator=len(valid),
        details={"reproducible_cases": [r.case_id for r in reproducible]},
    )


def compute_failure_localization_accuracy(runs: list[BenchmarkRun]) -> MetricSummary:
    invalid = [r for r in runs if r.expected_status == "Rejected"]
    localized = [
        r
        for r in invalid
        if r.expected_responsible_component
        and r.observed_responsible_component == r.expected_responsible_component
    ]
    missed = [r.case_id for r in invalid if r not in localized]
    return MetricSummary(
        name="failure_localization_accuracy",
        score=_safe_ratio(len(localized), len(invalid)),
        numerator=len(localized),
        denominator=len(invalid),
        details={"missed_localization": missed},
    )


def compute_certificate_completeness_score(runs: list[BenchmarkRun]) -> MetricSummary:
    """Score certificate field completeness on cases that expect valid certificates."""
    candidates = [r for r in runs if r.expected_status in ("Admitted", "Accepted")]
    scores: list[float] = []
    for run in candidates:
        analysis = _load_run_analysis(run)
        if "certificate_field_coverage" in analysis:
            scores.append(float(analysis["certificate_field_coverage"]))
        elif run.passed:
            scores.append(1.0)
        else:
            scores.append(0.0)
    if not candidates:
        return MetricSummary(
            name="certificate_completeness_score",
            score=1.0,
            numerator=0,
            denominator=0,
            details={"note": "no valid certificate cases"},
        )
    return MetricSummary(
        name="certificate_completeness_score",
        score=sum(scores) / len(scores),
        numerator=int(sum(scores)),
        denominator=len(scores),
        details={"per_case_scores": scores},
    )


def compute_registry_coverage_score(runs: list[BenchmarkRun]) -> MetricSummary:
    ratios: list[float] = []
    for run in runs:
        analysis = _load_run_analysis(run)
        if "registry_coverage" in analysis:
            ratios.append(float(analysis["registry_coverage"]))
    if ratios:
        return MetricSummary(
            name="registry_coverage_score",
            score=sum(ratios) / len(ratios),
            numerator=int(sum(ratios) * 100),
            denominator=len(ratios) * 100,
        )
    valid = [r for r in runs if r.expected_status in ("Admitted", "Accepted")]
    covered = [r for r in valid if r.passed]
    return MetricSummary(
        name="registry_coverage_score",
        score=_safe_ratio(len(covered), len(valid)),
        numerator=len(covered),
        denominator=len(valid),
    )


def compute_formal_check_coverage_score(runs: list[BenchmarkRun]) -> MetricSummary:
    formal = [
        r
        for r in runs
        if "formal" in r.case_id.lower()
        or "lean" in r.case_id.lower()
        or r.suite_id.startswith("formal")
    ]
    if not formal:
        return MetricSummary(
            name="formal_check_coverage_score",
            score=1.0,
            numerator=0,
            denominator=0,
            details={"note": "no formal cases in run"},
        )
    passed = [r for r in formal if r.passed]
    return MetricSummary(
        name="formal_check_coverage_score",
        score=_safe_ratio(len(passed), len(formal)),
        numerator=len(passed),
        denominator=len(formal),
    )


def compute_scientific_memory_interpretability_score(runs: list[BenchmarkRun]) -> MetricSummary:
    """Score rendered evidence sections on cases that expect full interpretability."""
    candidates = [r for r in runs if r.expected_status in ("Admitted", "Accepted")]
    coverages: list[float] = []
    for run in candidates:
        analysis = _load_run_analysis(run)
        if "rendered_section_coverage" in analysis:
            coverages.append(float(analysis["rendered_section_coverage"]))
        elif run.passed:
            coverages.append(1.0)
    if coverages:
        return MetricSummary(
            name="scientific_memory_interpretability_score",
            score=sum(coverages) / len(coverages),
            numerator=int(sum(coverages) * 100),
            denominator=len(coverages) * 100,
            details={"sections_found": coverages},
        )
    render_runs = [r for r in runs if any("render" in " ".join(c.command) for c in r.commands)]
    if not render_runs:
        return MetricSummary(
            name="scientific_memory_interpretability_score",
            score=1.0,
            numerator=0,
            denominator=0,
            details={"note": "no rendering commands or section sidecars"},
        )
    passed = [r for r in render_runs if all(c.exit_code == 0 for c in r.commands)]
    return MetricSummary(
        name="scientific_memory_interpretability_score",
        score=_safe_ratio(len(passed), len(render_runs)),
        numerator=len(passed),
        denominator=len(render_runs),
    )


def compute_repair_hint_quality_score(runs: list[BenchmarkRun]) -> MetricSummary:
    need_hint = [r for r in runs if r.expected_status == "Rejected" and r.expected_failure_code]
    acceptable = [
        r
        for r in need_hint
        if r.repair_hint_acceptable
        or r.observed_repair_hint
        or (r.observed_responsible_component and r.observed_failure_code)
    ]
    return MetricSummary(
        name="repair_hint_quality_score",
        score=_safe_ratio(len(acceptable), len(need_hint)),
        numerator=len(acceptable),
        denominator=len(need_hint),
        details={"cases_missing_hints": [r.case_id for r in need_hint if r not in acceptable]},
    )


def compute_cross_domain_portability_score(
    suite_scores: dict[str, float] | None = None,
    runs: list[BenchmarkRun] | None = None,
) -> MetricSummary:
    if suite_scores and len(suite_scores) >= 3:
        avg = sum(suite_scores.values()) / len(suite_scores)
        return MetricSummary(
            name="cross_domain_portability_score",
            score=avg,
            details={"per_suite": suite_scores},
        )
    if not runs:
        return MetricSummary(name="cross_domain_portability_score", score=1.0)

    workflow_runs: dict[str, list[BenchmarkRun]] = {}
    for run in runs:
        wf = _workflow_for_run(run)
        workflow_runs.setdefault(wf, []).append(run)

    domain_workflows = [
        "hospital_lab.qc_release",
        "agent_tool_use.safety_v0",
        "scientific_computation.reproducibility_v0",
    ]
    scores: list[float] = []
    for wf in domain_workflows:
        group = workflow_runs.get(wf, [])
        if not group:
            continue
        scores.append(sum(1 for r in group if r.passed) / len(group))
    score = sum(scores) / len(scores) if scores else 1.0
    per_wf = {
        wf: (sum(1 for r in workflow_runs.get(wf, []) if r.passed) / len(workflow_runs[wf]))
        if workflow_runs.get(wf)
        else None
        for wf in domain_workflows
    }
    return MetricSummary(
        name="cross_domain_portability_score",
        score=score,
        details={"per_workflow_pass_rate": per_wf},
    )


def _workflow_for_run(run: BenchmarkRun) -> str:
    if run.workflow_id:
        return run.workflow_id
    if "tool-use" in run.case_id or "tool_use" in run.case_id:
        return "agent_tool_use.safety_v0"
    if "computation" in run.case_id:
        return "scientific_computation.reproducibility_v0"
    if "lean" in run.case_id and "labtrust" not in run.case_id:
        return "pcs.formal_trust_kernel"
    if "render" in run.case_id or "formal-section" in run.case_id:
        return "pcs.scientific_memory"
    return "hospital_lab.qc_release"


METRIC_COMPUTERS = [
    compute_release_reproducibility_score,
    compute_failure_localization_accuracy,
    compute_certificate_completeness_score,
    compute_registry_coverage_score,
    compute_formal_check_coverage_score,
    compute_scientific_memory_interpretability_score,
    compute_repair_hint_quality_score,
]


def compute_all_metrics(
    runs: list[BenchmarkRun],
    suite_metric_filter: list[str] | None = None,
    suite_scores: dict[str, float] | None = None,
) -> list[MetricSummary]:
    summaries: list[MetricSummary] = []
    for fn in METRIC_COMPUTERS:
        summary = fn(runs)
        if suite_metric_filter and summary.name not in suite_metric_filter:
            continue
        summaries.append(summary)
    summaries.append(compute_cross_domain_portability_score(suite_scores=suite_scores, runs=runs))
    return summaries


def apply_metrics_to_report(report, summaries: list[MetricSummary]) -> None:
    report.metric_summaries = summaries
    report.metrics = {s.name: s.score for s in summaries}
    report.summary = {
        **report.summary,
        "total_runs": len(report.runs),
        "passed": sum(1 for r in report.runs if r.passed),
        "failed": sum(1 for r in report.runs if not r.passed),
    }
