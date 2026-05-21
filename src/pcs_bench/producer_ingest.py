"""Normalize producer-native benchmark outputs into pcs-bench reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pcs_bench.benchmark_vocabulary import KNOWN_METRIC_IDS
from pcs_bench.report_export import enrich_report_for_export, pcs_bench_source_commit
from pcs_bench.reports import report_digest
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary, RepoCommits

SUPPORTED_PRODUCERS = frozenset(
    {
        "certifyedge",
        "provability-fabric",
        "provability_fabric",
        "pf",
        "scientific-memory",
        "scientific_memory",
        "scimem",
        "labtrust",
        "labtrust-gym",
    }
)

_REPORT_CANDIDATES = (
    "benchmark_report.v0.json",
    "BenchmarkReport.v0.json",
    "report.json",
    "benchmark_report.json",
    "results.json",
)


def _find_report_file(input_dir: Path) -> Path | None:
    for name in _REPORT_CANDIDATES:
        path = input_dir / name
        if path.is_file():
            return path
    for path in sorted(input_dir.glob("*.json")):
        if path.name.endswith("-runs"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and ("runs" in data or "metric_summaries" in data):
            return path
    return None


def _normalize_run(raw: dict, *, suite_id: str, producer: str) -> BenchmarkRun:
    expected_status = raw.get("expected_status") or "passed"
    observed_status = raw.get("observed_status") or raw.get("status") or expected_status
    if observed_status in ("Admitted", "Accepted"):
        observed_status = "passed"
        system = "admitted"
    elif observed_status in ("Rejected",):
        observed_status = "failed"
        system = "rejected"
    else:
        system = raw.get("observed_system_outcome") or raw.get("system_outcome")
        if not system:
            system = "admitted" if observed_status == "passed" else "rejected"

    passed = raw.get("passed")
    if passed is None:
        passed = observed_status == expected_status

    return BenchmarkRun(
        run_id=raw.get("run_id") or raw.get("case_id", "unknown"),
        case_id=raw.get("case_id", "unknown"),
        suite_id=raw.get("suite_id") or suite_id,
        workflow_id=raw.get("workflow_id"),
        task_id=raw.get("task_id"),
        expected_status=expected_status,
        expected_system_outcome=raw.get("expected_system_outcome") or system,
        observed_status=observed_status if observed_status in ("passed", "failed", "skipped", "error") else ("passed" if passed else "failed"),
        observed_system_outcome=system,
        observed_failure_code=raw.get("observed_failure_code") or raw.get("failure_code"),
        expected_failure_code=raw.get("expected_failure_code"),
        observed_responsible_component=raw.get("observed_responsible_component")
        or raw.get("responsible_component"),
        expected_responsible_component=raw.get("expected_responsible_component"),
        observed_repair_hint=raw.get("observed_repair_hint") or raw.get("repair_hint"),
        passed=bool(passed),
        execution_kind=raw.get("execution_kind") or "live",
        responsible_repo=producer,
    )


def _metric_summaries_from_raw(data: dict) -> list[MetricSummary]:
    if data.get("metric_summaries"):
        return [MetricSummary.model_validate(s) for s in data["metric_summaries"]]
    metrics = data.get("metrics")
    summaries: list[MetricSummary] = []
    if isinstance(metrics, dict):
        for name, value in metrics.items():
            if name not in KNOWN_METRIC_IDS:
                continue
            if isinstance(value, dict):
                summaries.append(
                    MetricSummary(
                        name=name,
                        score=value.get("score"),
                        applicability=value.get("applicability", "measured"),
                        reason=value.get("reason"),
                    )
                )
            elif value is not None:
                summaries.append(
                    MetricSummary(name=name, score=float(value), applicability="measured")
                )
    elif isinstance(metrics, list):
        for name in metrics:
            if name in KNOWN_METRIC_IDS:
                summaries.append(MetricSummary(name=name, applicability="measured"))
    return summaries


def ingest_producer_output(
    producer: str,
    input_dir: Path,
    out_path: Path,
    *,
    pcs_core_path: Path | None = None,
    suite_id: str | None = None,
) -> BenchmarkReport:
    """Load a producer benchmark directory and write a normalized BenchmarkReport.v0."""
    producer_key = producer.lower().replace("_", "-")
    if producer_key not in SUPPORTED_PRODUCERS and producer not in SUPPORTED_PRODUCERS:
        raise ValueError(f"Unsupported producer: {producer}")

    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    report_file = _find_report_file(input_dir)
    if not report_file:
        raise FileNotFoundError(
            f"No benchmark report JSON found under {input_dir} "
            f"(tried {', '.join(_REPORT_CANDIDATES)})"
        )

    data: dict[str, Any] = json.loads(report_file.read_text(encoding="utf-8"))
    resolved_suite = suite_id or data.get("benchmark_suite_id") or producer_key

    runs_raw = data.get("runs") or []
    runs = [_normalize_run(r, suite_id=resolved_suite, producer=producer_key) for r in runs_raw]

    report = BenchmarkReport(
        benchmark_suite_id=resolved_suite,
        repo_commits=RepoCommits(**(data.get("repo_commits") or {})),
        runs=runs,
        metric_summaries=_metric_summaries_from_raw(data),
        summary=data.get("summary") or {},
        coverage=data.get("coverage") or {},
        failures=[],
    )
    if not report.summary.get("execution_mode"):
        report.summary["execution_mode"] = "live"
    if not report.summary.get("evidence_grade"):
        report.summary["evidence_grade"] = "release"
    report.summary.setdefault("live_cases", len(runs))
    report.summary.setdefault("simulated_cases", 0)
    report.summary.setdefault("hybrid_fallback_cases", 0)

    enrich_report_for_export(report)
    report.source_commit = data.get("source_commit") or pcs_bench_source_commit()
    report.finalize(digest=report_digest(report))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    from pcs_bench.report_export import to_benchmark_report_v0_dict

    runs_dir = out_path.parent / f"{out_path.stem}-runs"
    payload = to_benchmark_report_v0_dict(
        report, runs_output_dir=runs_dir, pcs_core_path=pcs_core_path
    )
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    if "metric_summaries" not in payload and report.metric_summaries:
        from pcs_bench.report_export import _metric_summaries_export

        companion = out_path.parent / f"{out_path.stem}-metric_summaries.v0.json"
        companion.write_text(
            json.dumps(
                {
                    "schema_version": "v0",
                    "metric_summaries": _metric_summaries_export(report.metric_summaries),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    return report
