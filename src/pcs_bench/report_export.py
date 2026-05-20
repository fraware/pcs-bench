"""Serialize and validate BenchmarkReport.v0 for pcs-core conformance."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pcs_bench.schemas import BenchmarkReport
from pcs_bench.validation import try_load_json_schema, validate_report_data_strict

PCS_BENCH_SOURCE_REPO = "https://github.com/fraware/pcs-bench"


def pcs_bench_source_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return "unknown"


def enrich_report_for_export(report: BenchmarkReport) -> BenchmarkReport:
    """Attach pcs-core required provenance fields."""
    report.source_repo = PCS_BENCH_SOURCE_REPO
    report.source_commit = pcs_bench_source_commit()
    if not report.signature_or_digest:
        from pcs_bench.reports import report_digest

        report.signature_or_digest = report_digest(report)
    return report


def metrics_to_pcs_core_dict(report: BenchmarkReport) -> dict[str, Any]:
    """Export metrics: measured scores as numbers; others as structured objects."""
    out: dict[str, Any] = {}
    for summary in report.metric_summaries:
        if summary.applicability == "measured" and summary.score is not None:
            out[summary.name] = round(summary.score, 6)
        else:
            out[summary.name] = {
                "score": summary.score,
                "applicability": summary.applicability,
                "reason": summary.reason or summary.details.get("note", ""),
            }
    return out


def to_benchmark_report_v0_dict(report: BenchmarkReport) -> dict[str, Any]:
    """Canonical JSON dict for pcs-core BenchmarkReport.v0."""
    report = enrich_report_for_export(report)
    data = report.model_dump(mode="json")
    data["metrics"] = metrics_to_pcs_core_dict(report)
    data["source_repo"] = report.source_repo
    data["source_commit"] = report.source_commit
    data["signature_or_digest"] = report.signature_or_digest
    if not data.get("completed_at"):
        report.finalize()
        data["completed_at"] = report.completed_at
        data["signature_or_digest"] = report.signature_or_digest
    return data


def validate_report_strict(
    report: BenchmarkReport | dict[str, Any],
    config,
    *,
    schema_source: Path | None = None,
) -> list[str]:
    if isinstance(report, BenchmarkReport):
        data = to_benchmark_report_v0_dict(report)
    else:
        data = report
    pcs_core = schema_source or config.repos.pcs_core
    return validate_report_data_strict(data, pcs_core)
