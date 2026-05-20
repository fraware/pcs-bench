"""Core benchmark metrics computation with honest applicability."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.benchmark_vocabulary import is_invalid_release_case, is_valid_release_case
from pcs_bench.metrics_applicability import insufficient, measured, not_applicable
from pcs_bench.metrics_definitions import (
    CERTIFICATE_REQUIRED_FIELDS,
    REQUIRED_MEMORY_SECTIONS,
)
from pcs_bench.schemas import BenchmarkRun, MetricSummary

__all__ = [
    "CERTIFICATE_REQUIRED_FIELDS",
    "REQUIRED_MEMORY_SECTIONS",
    "compute_all_metrics",
    "apply_metrics_to_report",
    "METRIC_COMPUTERS",
    "ALL_METRIC_NAMES",
]

ALL_METRIC_NAMES = [
    "release_reproducibility_score",
    "failure_localization_accuracy",
    "certificate_completeness_score",
    "registry_coverage_score",
    "formal_check_coverage_score",
    "scientific_memory_interpretability_score",
    "repair_hint_quality_score",
    "cross_domain_portability_score",
]

SUITE_ALL_REQUIRED_METRICS = ALL_METRIC_NAMES.copy()


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
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


def _is_formal_run(run: BenchmarkRun) -> bool:
    return (
        "formal" in run.case_id.lower()
        or "lean" in run.case_id.lower()
        or (run.suite_id or "").startswith("formal")
        or run.workflow_id == "pcs.formal_trust_kernel"
    )


def _is_memory_run(run: BenchmarkRun) -> bool:
    return (
        "render" in run.case_id.lower()
        or "memory" in (run.suite_id or "")
        or run.workflow_id == "pcs.scientific_memory"
    )


def compute_release_reproducibility_score(runs: list[BenchmarkRun]) -> MetricSummary:
    valid = [r for r in runs if is_valid_release_case(r.expected_status, r.expected_system_outcome)]
    if not valid:
        return insufficient(
            "release_reproducibility_score",
            "No valid release cases were present in this run.",
        )
    reproducible = [r for r in valid if r.passed]
    score = _safe_ratio(len(reproducible), len(valid))
    return measured(
        "release_reproducibility_score",
        score,
        numerator=len(reproducible),
        denominator=len(valid),
        details={"reproducible_cases": [r.case_id for r in reproducible]},
    )


def compute_failure_localization_accuracy(runs: list[BenchmarkRun]) -> MetricSummary:
    invalid = [r for r in runs if is_invalid_release_case(r.expected_status, r.expected_system_outcome)]
    if not invalid:
        return insufficient(
            "failure_localization_accuracy",
            "No rejected cases were present to evaluate localization.",
        )
    localized = [
        r
        for r in invalid
        if r.expected_responsible_component
        and r.observed_responsible_component == r.expected_responsible_component
    ]
    missed = [r.case_id for r in invalid if r not in localized]
    return measured(
        "failure_localization_accuracy",
        _safe_ratio(len(localized), len(invalid)),
        numerator=len(localized),
        denominator=len(invalid),
        details={"missed_localization": missed},
    )


def compute_certificate_completeness_score(runs: list[BenchmarkRun]) -> MetricSummary:
    candidates = [r for r in runs if is_valid_release_case(r.expected_status, r.expected_system_outcome)]
    if not candidates:
        return insufficient(
            "certificate_completeness_score",
            "No cases expecting valid certificates were present.",
        )
    scores: list[float] = []
    for run in candidates:
        analysis = _load_run_analysis(run)
        if "certificate_field_coverage" in analysis:
            scores.append(float(analysis["certificate_field_coverage"]))
        elif run.passed:
            scores.append(1.0)
        else:
            scores.append(0.0)
    return measured(
        "certificate_completeness_score",
        sum(scores) / len(scores),
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
        return measured(
            "registry_coverage_score",
            sum(ratios) / len(ratios),
            numerator=int(sum(ratios) * 100),
            denominator=len(ratios) * 100,
        )
    valid = [r for r in runs if is_valid_release_case(r.expected_status, r.expected_system_outcome)]
    if not valid:
        return insufficient(
            "registry_coverage_score",
            "No registry-bearing valid cases were present.",
        )
    covered = [r for r in valid if r.passed]
    return measured(
        "registry_coverage_score",
        _safe_ratio(len(covered), len(valid)),
        numerator=len(covered),
        denominator=len(valid),
    )


def compute_formal_check_coverage_score(runs: list[BenchmarkRun]) -> MetricSummary:
    formal = [r for r in runs if _is_formal_run(r)]
    if not formal:
        return insufficient(
            "formal_check_coverage_score",
            "No formal-check cases were present in this suite.",
        )
    passed = [r for r in formal if r.passed]
    return measured(
        "formal_check_coverage_score",
        _safe_ratio(len(passed), len(formal)),
        numerator=len(passed),
        denominator=len(formal),
    )


def compute_scientific_memory_interpretability_score(runs: list[BenchmarkRun]) -> MetricSummary:
    memory_runs = [r for r in runs if _is_memory_run(r)]
    if not memory_runs:
        return insufficient(
            "scientific_memory_interpretability_score",
            "No Scientific Memory rendering cases were present.",
        )
    coverages: list[float] = []
    for run in memory_runs:
        if not is_valid_release_case(run.expected_status, run.expected_system_outcome):
            continue
        analysis = _load_run_analysis(run)
        if "rendered_section_coverage" in analysis:
            coverages.append(float(analysis["rendered_section_coverage"]))
        elif run.passed:
            coverages.append(1.0)
        else:
            coverages.append(0.0)
    if coverages:
        return measured(
            "scientific_memory_interpretability_score",
            sum(coverages) / len(coverages),
            numerator=int(sum(coverages) * 100),
            denominator=len(coverages) * 100,
            details={"sections_found": coverages},
        )
    render_runs = [r for r in memory_runs if any("render" in " ".join(c.command) for c in r.commands)]
    if not render_runs:
        return insufficient(
            "scientific_memory_interpretability_score",
            "No rendering commands or section sidecars for memory cases.",
        )
    passed = [r for r in render_runs if all(c.exit_code == 0 for c in r.commands)]
    return measured(
        "scientific_memory_interpretability_score",
        _safe_ratio(len(passed), len(render_runs)),
        numerator=len(passed),
        denominator=len(render_runs),
    )


def compute_repair_hint_quality_score(runs: list[BenchmarkRun]) -> MetricSummary:
    need_hint = [
        r
        for r in runs
        if is_invalid_release_case(r.expected_status, r.expected_system_outcome)
        and r.expected_failure_code
    ]
    if not need_hint:
        return insufficient(
            "repair_hint_quality_score",
            "No rejected cases with expected failure codes for repair hints.",
        )
    acceptable = [
        r
        for r in need_hint
        if r.repair_hint_acceptable
        or r.observed_repair_hint
        or (r.observed_responsible_component and r.observed_failure_code)
    ]
    return measured(
        "repair_hint_quality_score",
        _safe_ratio(len(acceptable), len(need_hint)),
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
        return measured(
            "cross_domain_portability_score",
            avg,
            details={"per_suite": suite_scores},
        )
    if not runs:
        return insufficient(
            "cross_domain_portability_score",
            "No runs available for cross-domain scoring.",
        )

    workflow_runs: dict[str, list[BenchmarkRun]] = {}
    for run in runs:
        wf = _workflow_for_run(run)
        workflow_runs.setdefault(wf, []).append(run)

    domain_workflows = [
        "hospital_lab.qc_release",
        "agent_tool_use.safety_v0",
        "scientific_computation.reproducibility_v0",
    ]
    present = [wf for wf in domain_workflows if workflow_runs.get(wf)]
    if len(present) < 2:
        return insufficient(
            "cross_domain_portability_score",
            "Fewer than two PCS workflow domains present for portability scoring.",
            details={"workflows_present": present},
        )
    scores = [
        sum(1 for r in workflow_runs[wf] if r.passed) / len(workflow_runs[wf])
        for wf in present
    ]
    per_wf = {
        wf: (sum(1 for r in workflow_runs.get(wf, []) if r.passed) / len(workflow_runs[wf]))
        if workflow_runs.get(wf)
        else None
        for wf in domain_workflows
    }
    return measured(
        "cross_domain_portability_score",
        sum(scores) / len(scores),
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


def resolve_required_metrics(
    suite_ids: list[str],
    suite_configs: dict[str, list[str] | None],
) -> set[str]:
    required: set[str] = set()
    if "all" in suite_ids or len(suite_ids) > 1:
        return set(SUITE_ALL_REQUIRED_METRICS)
    for sid in suite_ids:
        metrics = suite_configs.get(sid)
        if metrics:
            required.update(metrics)
    return required


def compute_all_metrics(
    runs: list[BenchmarkRun],
    *,
    required_metrics: set[str] | None = None,
    optional_metrics: set[str] | None = None,
    suite_metric_filter: list[str] | None = None,
    suite_scores: dict[str, float] | None = None,
) -> list[MetricSummary]:
    summaries: list[MetricSummary] = []
    for fn in METRIC_COMPUTERS:
        summary = fn(runs)
        if suite_metric_filter and summary.name not in suite_metric_filter:
            continue
        summaries.append(summary)
    cross = compute_cross_domain_portability_score(suite_scores=suite_scores, runs=runs)
    if not suite_metric_filter or cross.name in suite_metric_filter:
        summaries.append(cross)

    req = required_metrics or set()
    opt = optional_metrics or set()
    adjusted: list[MetricSummary] = []
    for summary in summaries:
        if summary.name in req and summary.applicability == "insufficient_cases":
            adjusted.append(
                MetricSummary(
                    name=summary.name,
                    score=None,
                    applicability="failed_to_measure",
                    reason=(
                        f"Required metric {summary.name} could not be measured: "
                        f"{summary.reason}"
                    ),
                    details=summary.details,
                )
            )
        elif summary.name in opt and summary.applicability == "insufficient_cases":
            adjusted.append(
                not_applicable(
                    summary.name,
                    summary.reason or "Optional metric not applicable for this suite.",
                )
            )
        else:
            adjusted.append(summary)
    return adjusted


def apply_metrics_to_report(report, summaries: list[MetricSummary]) -> None:
    report.metric_summaries = summaries
    report.metrics = [
        s.name
        for s in summaries
        if s.applicability == "measured" and s.score is not None
    ]
    report.summary = {
        **report.summary,
        "total_runs": len(report.runs),
        "passed": sum(1 for r in report.runs if r.passed),
        "failed": sum(1 for r in report.runs if not r.passed),
        "measured_metrics": [s.name for s in summaries if s.applicability == "measured"],
        "skipped_metrics": [
            {"name": s.name, "applicability": s.applicability, "reason": s.reason}
            for s in summaries
            if s.applicability != "measured"
        ],
    }
