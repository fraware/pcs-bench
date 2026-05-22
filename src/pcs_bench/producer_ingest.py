"""Normalize producer PcsBenchIngest.v0 outputs into pcs-bench BenchmarkReport.v0."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pcs_bench.benchmark_vocabulary import KNOWN_METRIC_IDS
from pcs_bench.ingest_validation import (
    KNOWN_PRODUCER_IDS,
    canonical_producer_id,
    load_ingest_document,
    validate_ingest_data_strict,
    validate_ingest_developer_warnings,
)
from pcs_bench.report_export import enrich_report_for_export, pcs_bench_source_commit
from pcs_bench.reports import report_digest
from pcs_bench.schemas import (
    BenchmarkReport,
    BenchmarkRun,
    CommandRecord,
    MetricSummary,
    RepoCommits,
)

_METRIC_TO_COVERAGE_KEY: dict[str, str] = {
    "registry_coverage": "registry",
    "registry_coverage_score": "registry",
    "formal_check_coverage": "formal_checks",
    "formal_check_coverage_score": "formal_checks",
    "scientific_memory": "scientific_memory",
    "scientific_memory_interpretability_score": "scientific_memory",
    "release_reproducibility": "release_reproducibility",
    "release_reproducibility_score": "release_reproducibility",
    "certificate_completeness": "certificate_completeness",
    "certificate_completeness_score": "certificate_completeness",
}

_METRIC_FROM_COVERAGE: dict[str, str] = {
    "registry": "registry_coverage_score",
    "formal_checks": "formal_check_coverage_score",
    "scientific_memory": "scientific_memory_interpretability_score",
    "release_reproducibility": "release_reproducibility_score",
    "certificate_completeness": "certificate_completeness_score",
}


def _normalize_run(
    raw: dict[str, Any],
    *,
    suite_id: str,
    producer: str,
    fl_by_run: dict[str, dict[str, Any]],
) -> BenchmarkRun:
    fl = fl_by_run.get(raw.get("run_id", ""), {})
    system = raw.get("system_admission_outcome") or (
        "admitted" if raw.get("observed_status") == "passed" else "rejected"
    )
    expected_status = "passed" if system == "admitted" else "failed"
    passed = fl.get("localized_correctly") if fl else raw.get("observed_status") == expected_status

    commands: list[CommandRecord] = []
    for entry in raw.get("commands") or []:
        if not isinstance(entry, dict):
            continue
        cmd_text = entry.get("command", "")
        commands.append(
            CommandRecord(
                command=cmd_text.split() if isinstance(cmd_text, str) else list(cmd_text),
                cwd=".",
                exit_code=int(entry.get("exit_code", 0)),
                started_at=str(raw.get("started_at") or ""),
                completed_at=str(raw.get("completed_at") or ""),
                duration_ms=int(raw.get("duration_ms", 0)),
            )
        )

    artifacts = [str(a) for a in (raw.get("artifacts_produced") or []) if a]

    return BenchmarkRun(
        run_id=raw.get("run_id") or raw.get("case_id", "unknown"),
        case_id=raw.get("case_id", "unknown"),
        suite_id=suite_id,
        workflow_id=raw.get("workflow_id"),
        task_id=raw.get("task_id"),
        expected_status=expected_status,
        expected_system_outcome=system,
        observed_status=str(raw.get("observed_status") or expected_status),
        observed_system_outcome=system,
        observed_failure_code=raw.get("observed_failure_code") or fl.get("observed_failure_code"),
        expected_failure_code=fl.get("expected_failure_code"),
        observed_responsible_component=raw.get("observed_responsible_component")
        or fl.get("observed_responsible_component"),
        expected_responsible_component=fl.get("expected_responsible_component"),
        observed_repair_hint=raw.get("observed_repair_hint"),
        passed=bool(passed),
        execution_kind="live",
        responsible_repo=producer,
        commands=commands,
        artifacts=artifacts,
        duration_ms=int(raw.get("duration_ms", 0)),
    )


def _metric_summaries_from_ingest(
    data: dict[str, Any], coverage: dict[str, Any]
) -> list[MetricSummary]:
    summaries: list[MetricSummary] = []
    for key, report in coverage.items():
        metric_name = _METRIC_FROM_COVERAGE.get(key)
        if not metric_name or not isinstance(report, dict):
            continue
        ratio = report.get("coverage_ratio")
        summaries.append(
            MetricSummary(
                name=metric_name,
                score=float(ratio) if ratio is not None else None,
                applicability="measured",
            )
        )

    for report in data.get("explain_quality_reports") or []:
        if not isinstance(report, dict):
            continue
        score = report.get("quality_score")
        if score is not None:
            summaries.append(
                MetricSummary(
                    name="scientific_memory_interpretability_score",
                    score=float(score),
                    applicability="measured",
                    reason=f"explain_quality:{report.get('case_id', 'unknown')}",
                )
            )
            break

    if not summaries:
        summaries.append(
            MetricSummary(name="release_reproducibility_score", applicability="measured")
        )
    return summaries


def _coverage_block_from_ingest(data: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for report in data.get("coverage_reports") or []:
        if not isinstance(report, dict):
            continue
        metric = str(report.get("metric_id") or report.get("metric") or "")
        key = _METRIC_TO_COVERAGE_KEY.get(metric)
        if key and key not in block:
            block[key] = report

    explain_reports = data.get("explain_quality_reports") or []
    if explain_reports and isinstance(explain_reports[0], dict):
        block["explain_quality"] = explain_reports[0]

    profile_reports = data.get("profile_coverage_reports") or []
    if profile_reports and isinstance(profile_reports[0], dict):
        block["profile_coverage"] = profile_reports[0]

    return block


def _preserve_artifact_refs(
    artifact_refs: list[Any], *, base_dir: Path
) -> list[str]:
    paths: list[str] = []
    refs_dir = base_dir / "artifact_refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    for idx, entry in enumerate(artifact_refs or []):
        if not isinstance(entry, dict):
            continue
        ref_id = entry.get("path", f"ref-{idx}").replace("/", "_")
        if ref_id.endswith(".json"):
            dest = refs_dir / ref_id
        else:
            dest = refs_dir / f"{ref_id}.json"
        dest.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        paths.append(str(dest.as_posix()))
    return paths


def ingest_from_pcs_bench_ingest(
    data: dict[str, Any],
    *,
    producer: str,
    base_dir: Path,
    suite_id: str | None = None,
) -> BenchmarkReport:
    """Build internal BenchmarkReport from a validated PcsBenchIngest.v0 document."""
    producer_key = canonical_producer_id(producer)
    if producer_key not in KNOWN_PRODUCER_IDS:
        raise ValueError(f"Unsupported producer: {producer}")

    resolved_suite = suite_id or data.get("suite_id") or producer_key
    fl_by_run = {
        str(r.get("run_id")): r
        for r in data.get("failure_localization_reports") or []
        if isinstance(r, dict) and r.get("run_id")
    }
    runs = [
        _normalize_run(
            r,
            suite_id=resolved_suite,
            producer=producer_key,
            fl_by_run=fl_by_run,
        )
        for r in data.get("benchmark_runs") or []
        if isinstance(r, dict)
    ]

    ref_paths = _preserve_artifact_refs(data.get("artifact_refs") or [], base_dir=base_dir)
    for run in runs:
        run.artifacts.extend(ref_paths)

    coverage = _coverage_block_from_ingest(data)
    live_count = len(runs)
    summary = {
        "execution_mode": "live" if live_count else "simulate",
        "evidence_grade": "release" if live_count else "developer",
        "live_cases": live_count,
        "simulated_cases": 0 if live_count else 1,
        "hybrid_fallback_cases": 0,
        "producer_ingest_id": data.get("producer_id"),
        "workflow_id": data.get("workflow_id"),
    }

    report = BenchmarkReport(
        benchmark_suite_id=resolved_suite,
        repo_commits=RepoCommits(**(data.get("repo_commits") or {})),
        runs=runs,
        metric_summaries=_metric_summaries_from_ingest(data, coverage),
        summary=summary,
        coverage=coverage,
        failures=[],
    )
    report.source_repo = data.get("source_repo")
    report.source_commit = data.get("source_commit")
    return report


@dataclass
class ProducerMergeEntry:
    producer_id: str
    suite_id: str
    workflow_id: str
    source_repo: str
    source_commit: str
    ingest_digest: str
    ingest_path: str = ""
    normalized_path: str = ""
    live_cases: int = 0
    coverage_count: int = 0
    explain_count: int = 0
    failure_localization_count: int = 0
    profile_coverage_count: int = 0


def merge_benchmark_reports(
    reports: list[BenchmarkReport],
    *,
    suite_id: str = "all",
    producer_entries: list[ProducerMergeEntry] | None = None,
) -> BenchmarkReport:
    """Merge multiple BenchmarkReport instances into one aggregate report."""
    if not reports:
        raise ValueError("No reports to merge")

    merged = BenchmarkReport(benchmark_suite_id=suite_id)
    seen_run_ids: set[str] = set()
    metric_by_name: dict[str, MetricSummary] = {}
    coverage: dict[str, Any] = {}

    for report in reports:
        for run in report.runs:
            if run.run_id in seen_run_ids:
                continue
            seen_run_ids.add(run.run_id)
            merged.runs.append(run)
        for summary in report.metric_summaries:
            metric_by_name[summary.name] = summary
        for key, value in report.coverage.items():
            if key not in coverage:
                coverage[key] = value
        merged.failures.extend(report.failures)
        for field, value in report.repo_commits.model_dump().items():
            if value and value != "unknown":
                setattr(merged.repo_commits, field, value)

    merged.metric_summaries = list(metric_by_name.values()) or [
        MetricSummary(name=name, applicability="measured") for name in KNOWN_METRIC_IDS[:1]
    ]
    merged.coverage = coverage
    merged.summary = {
        "execution_mode": "live",
        "evidence_grade": "release",
        "live_cases": sum(1 for r in merged.runs if r.execution_kind == "live"),
        "simulated_cases": sum(1 for r in merged.runs if r.execution_kind == "simulate"),
        "hybrid_fallback_cases": sum(
            1 for r in merged.runs if r.execution_kind not in ("live", "simulate")
        ),
        "producer_reports_merged": len(producer_entries) if producer_entries else len(reports),
    }
    return merged


def write_producer_merge_manifest(out_path: Path, entries: list[ProducerMergeEntry]) -> Path:
    """Write auditable producer provenance sidecar next to aggregate report."""
    manifest_path = out_path.parent / "producer_merge_manifest.v0.json"
    payload = {
        "schema_version": "v0",
        "aggregate_report_path": str(out_path.resolve()),
        "aggregate_report": out_path.name,
        "producer_reports": [
            {
                "producer_id": e.producer_id,
                "suite_id": e.suite_id,
                "workflow_id": e.workflow_id,
                "source_repo": e.source_repo,
                "source_commit": e.source_commit,
                "ingest_digest": e.ingest_digest,
                "ingest_path": e.ingest_path,
                "normalized_report_path": e.normalized_path,
                "normalized_path": e.normalized_path,
                "live_cases": e.live_cases,
                "coverage_count": e.coverage_count,
                "explain_count": e.explain_count,
                "failure_localization_count": e.failure_localization_count,
                "profile_coverage_count": e.profile_coverage_count,
            }
            for e in entries
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def ingest_producer_output(
    producer: str,
    input_path: Path,
    out_path: Path,
    *,
    pcs_core_path: Path | None = None,
    suite_id: str | None = None,
    validate: bool = True,
    release_grade: bool = False,
    producer_repo: Path | None = None,
) -> BenchmarkReport:
    """Load PcsBenchIngest.v0 and write a normalized BenchmarkReport.v0."""
    data, base_dir = load_ingest_document(input_path)

    root = pcs_core_path if pcs_core_path and pcs_core_path.is_dir() else Path(__file__).resolve().parent
    if validate:
        ingest_file = input_path if input_path.is_file() else base_dir / "pcs_bench_ingest.v0.json"
        search_roots: tuple[Path, ...] = ()
        if producer_repo and producer_repo.is_dir():
            search_roots = (producer_repo.resolve(), base_dir.resolve())
        elif base_dir.is_dir():
            search_roots = (base_dir.resolve(),)
        errors = validate_ingest_data_strict(
            data,
            root,
            ingest_file=ingest_file if ingest_file.is_file() else None,
            release_grade=release_grade,
            search_roots=search_roots,
        )
        if errors:
            raise ValueError("; ".join(errors))
        if not release_grade:
            warnings = validate_ingest_developer_warnings(data, search_roots=search_roots)
            if warnings:
                import sys

                for warning in warnings:
                    print(warning, file=sys.stderr)

    report = ingest_from_pcs_bench_ingest(
        data,
        producer=producer,
        base_dir=out_path.parent,
        suite_id=suite_id,
    )
    enrich_report_for_export(report)
    if not report.source_commit:
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

    return report
