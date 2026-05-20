"""Aggregate coverage statistics for BenchmarkReport.coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pcs_bench.metrics import _load_run_analysis
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun


def _analysis_for_run(run: BenchmarkRun) -> dict[str, Any]:
    return _load_run_analysis(run)


def compute_coverage(report: BenchmarkReport) -> dict[str, Any]:
    """Build coverage block aligned with pcs-core CoverageReport concepts."""
    runs = report.runs
    from pcs_bench.benchmark_vocabulary import is_invalid_release_case, is_valid_release_case

    invalid = [r for r in runs if is_invalid_release_case(r.expected_status, r.expected_system_outcome)]
    valid = [r for r in runs if is_valid_release_case(r.expected_status, r.expected_system_outcome)]

    registry_ratios = []
    cert_scores = []
    render_scores = []
    missing_registry: list[str] = []
    missing_cert_fields: list[str] = []
    missing_sections: list[str] = []

    for run in runs:
        analysis = _analysis_for_run(run)
        if not analysis:
            continue
        reg = analysis.get("registry_coverage")
        if reg is not None:
            registry_ratios.append(float(reg))
            if float(reg) < 1.0 and run.case_id:
                missing_registry.append(run.case_id)
        cert = analysis.get("certificate_field_coverage")
        if cert is not None:
            cert_scores.append(float(cert))
        render = analysis.get("rendered_section_coverage")
        if render is not None:
            render_scores.append(float(render))
            if float(render) < 1.0 and is_valid_release_case(
                run.expected_status, run.expected_system_outcome
            ):
                missing_sections.append(run.case_id)

    localized = sum(
        1
        for r in invalid
        if r.observed_responsible_component == r.expected_responsible_component
    )

    return {
        "suites_exercised": sorted({r.suite_id for r in runs}),
        "cases_total": len(runs),
        "cases_passed": sum(1 for r in runs if r.passed),
        "valid_cases": len(valid),
        "invalid_cases": len(invalid),
        "failure_localization": {
            "localized": localized,
            "total_invalid": len(invalid),
            "accuracy": localized / len(invalid) if invalid else 1.0,
        },
        "registry": {
            "mean_coverage": sum(registry_ratios) / len(registry_ratios) if registry_ratios else None,
            "cases_below_full": missing_registry,
        },
        "certificates": {
            "mean_field_coverage": sum(cert_scores) / len(cert_scores) if cert_scores else None,
        },
        "rendering": {
            "mean_section_coverage": sum(render_scores) / len(render_scores) if render_scores else None,
            "cases_below_full": missing_sections,
        },
        "workflows": sorted({r.case_id.split("-")[0] for r in runs}),
    }


def apply_coverage_to_report(report: BenchmarkReport) -> None:
    report.coverage = compute_coverage(report)
