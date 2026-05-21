"""Baseline comparison between benchmark reports."""

from __future__ import annotations

from dataclasses import dataclass, field

from pcs_bench.schemas import BenchmarkReport


@dataclass
class MetricChange:
    name: str
    old_score: float
    new_score: float
    direction: str  # improved | regressed | unchanged

    @property
    def delta(self) -> float:
        return self.new_score - self.old_score


@dataclass
class ComparisonReport:
    metric_changes: list[MetricChange] = field(default_factory=list)
    new_failing_cases: list[str] = field(default_factory=list)
    fixed_cases: list[str] = field(default_factory=list)
    changed_failure_codes: list[dict] = field(default_factory=list)
    changed_responsible_components: list[dict] = field(default_factory=list)
    duration_changes: list[dict] = field(default_factory=list)
    rendering_regressions: list[dict] = field(default_factory=list)
    repair_hint_regressions: list[dict] = field(default_factory=list)

    def regressions(self) -> list[MetricChange]:
        return [m for m in self.metric_changes if m.direction == "regressed"]

    def improvements(self) -> list[MetricChange]:
        return [m for m in self.metric_changes if m.direction == "improved"]


def compare_reports(old: BenchmarkReport, new: BenchmarkReport) -> ComparisonReport:
    result = ComparisonReport()

    def _scores(report: BenchmarkReport) -> dict[str, float]:
        out: dict[str, float] = {}
        for summary in report.metric_summaries:
            if summary.score is not None:
                out[summary.name] = summary.score
        if isinstance(report.metrics, dict):
            out.update({k: float(v) for k, v in report.metrics.items() if isinstance(v, (int, float))})
        elif isinstance(report.metrics, list):
            for name in report.metrics:
                out.setdefault(name, 0.0)
        return out

    old_scores = _scores(old)
    new_scores = _scores(new)
    all_metrics = set(old_scores.keys()) | set(new_scores.keys())
    for name in sorted(all_metrics):
        old_score = old_scores.get(name, 0.0)
        new_score = new_scores.get(name, 0.0)
        if new_score > old_score + 1e-9:
            direction = "improved"
        elif new_score < old_score - 1e-9:
            direction = "regressed"
        else:
            direction = "unchanged"
        result.metric_changes.append(
            MetricChange(name=name, old_score=old_score, new_score=new_score, direction=direction)
        )

    old_by_case = {r.case_id: r for r in old.runs}
    new_by_case = {r.case_id: r for r in new.runs}

    for case_id, new_run in new_by_case.items():
        old_run = old_by_case.get(case_id)
        if old_run is None:
            if not new_run.passed:
                result.new_failing_cases.append(case_id)
            continue
        if old_run.passed and not new_run.passed:
            result.new_failing_cases.append(case_id)
        if not old_run.passed and new_run.passed:
            result.fixed_cases.append(case_id)
        if old_run.observed_failure_code != new_run.observed_failure_code:
            result.changed_failure_codes.append(
                {
                    "case_id": case_id,
                    "old": old_run.observed_failure_code,
                    "new": new_run.observed_failure_code,
                }
            )
        if old_run.observed_responsible_component != new_run.observed_responsible_component:
            result.changed_responsible_components.append(
                {
                    "case_id": case_id,
                    "old": old_run.observed_responsible_component,
                    "new": new_run.observed_responsible_component,
                }
            )
        if old_run.duration_ms != new_run.duration_ms:
            result.duration_changes.append(
                {
                    "case_id": case_id,
                    "old_ms": old_run.duration_ms,
                    "new_ms": new_run.duration_ms,
                }
            )
        old_render = _rendering_score(old_run)
        new_render = _rendering_score(new_run)
        if old_render is not None and new_render is not None and new_render < old_render - 1e-9:
            result.rendering_regressions.append(
                {"case_id": case_id, "old": old_render, "new": new_render}
            )
        if old_run.repair_hint_acceptable and not new_run.repair_hint_acceptable:
            result.repair_hint_regressions.append({"case_id": case_id})

    return result


def _rendering_score(run) -> float | None:
    from pcs_bench.metrics import _load_run_analysis

    analysis = _load_run_analysis(run)
    val = analysis.get("rendered_section_coverage")
    return float(val) if val is not None else None


def comparison_to_dict(comparison: ComparisonReport) -> dict:
    return {
        "regressions": [
            {"name": m.name, "old": m.old_score, "new": m.new_score, "delta": m.delta}
            for m in comparison.regressions()
        ],
        "improvements": [
            {"name": m.name, "old": m.old_score, "new": m.new_score, "delta": m.delta}
            for m in comparison.improvements()
        ],
        "new_failing_cases": comparison.new_failing_cases,
        "fixed_cases": comparison.fixed_cases,
        "changed_failure_codes": comparison.changed_failure_codes,
        "changed_responsible_components": comparison.changed_responsible_components,
        "rendering_regressions": comparison.rendering_regressions,
        "repair_hint_regressions": comparison.repair_hint_regressions,
        "duration_changes": comparison.duration_changes,
    }


def format_comparison_text(comparison: ComparisonReport) -> str:
    lines: list[str] = ["# Benchmark Comparison", ""]

    regressions = comparison.regressions()
    if regressions:
        lines.append("## Regressions")
        for m in regressions:
            lines.append(
                f"- **{m.name}** decreased from {m.old_score:.2f} to {m.new_score:.2f}"
            )
        lines.append("")

    improvements = comparison.improvements()
    if improvements:
        lines.append("## Improvements")
        for m in improvements:
            lines.append(
                f"- **{m.name}** increased from {m.old_score:.2f} to {m.new_score:.2f}"
            )
        lines.append("")

    if comparison.new_failing_cases:
        lines.append("## New failing cases")
        for c in comparison.new_failing_cases:
            lines.append(f"- {c}")
        lines.append("")

    if comparison.fixed_cases:
        lines.append("## Fixed cases")
        for c in comparison.fixed_cases:
            lines.append(f"- {c}")
        lines.append("")

    if comparison.changed_failure_codes:
        lines.append("## Changed failure codes")
        for item in comparison.changed_failure_codes:
            lines.append(f"- {item['case_id']}: {item['old']} -> {item['new']}")
        lines.append("")

    if comparison.changed_responsible_components:
        lines.append("## Changed responsible components")
        for item in comparison.changed_responsible_components:
            lines.append(f"- {item['case_id']}: {item['old']} -> {item['new']}")
        lines.append("")

    if comparison.rendering_regressions:
        lines.append("## Rendering coverage regressions")
        for item in comparison.rendering_regressions:
            lines.append(f"- {item['case_id']}: {item['old']:.2f} -> {item['new']:.2f}")
        lines.append("")

    if comparison.repair_hint_regressions:
        lines.append("## Repair hint quality regressions")
        for item in comparison.repair_hint_regressions:
            lines.append(f"- {item['case_id']}")
        lines.append("")

    return "\n".join(lines)
