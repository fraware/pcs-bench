"""Serialize BenchmarkReport.v0 for strict pcs-core conformance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pcs_bench.benchmark_vocabulary import (
    KNOWN_METRIC_IDS,
    benchmark_status_for_run,
)
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary

PCS_BENCH_SOURCE_REPO = "https://github.com/fraware/pcs-bench"
PLACEHOLDER_COMMITS = frozenset({"placeholder", "unknown", "deadbeef"})

_PKG_ROOT = Path(__file__).resolve().parent


def pcs_bench_source_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            if len(commit) == 40 and all(c in "0123456789abcdef" for c in commit):
                return commit
    except OSError:
        pass
    return "0000000000000000000000000000000000000001"


def fixture_source_commit() -> str:
    """40-char commit for benchmark case fixtures (pcs-bench tree)."""
    commit = pcs_bench_source_commit()
    if commit in PLACEHOLDER_COMMITS or len(commit) != 40:
        return "a1b2c3d4e5f6789012345678901234567890abcd"
    return commit


def enrich_report_for_export(report: BenchmarkReport) -> BenchmarkReport:
    report.source_repo = PCS_BENCH_SOURCE_REPO
    report.source_commit = pcs_bench_source_commit()
    if not report.signature_or_digest:
        from pcs_bench.reports import report_digest

        report.signature_or_digest = report_digest(report)
    return report


def _summary_scores(report: BenchmarkReport) -> dict[str, float]:
    scores: dict[str, float] = {}
    for summary in report.metric_summaries:
        if summary.applicability == "measured" and summary.score is not None:
            scores[summary.name] = summary.score
    return scores


def _is_pcs_core_coverage_entry(value: Any) -> bool:
    """True when value is a producer CoverageReport.v0 or ExplainQualityReport.v0 object."""
    if not isinstance(value, dict) or value.get("schema_version") != "v0":
        return False
    return "coverage_id" in value or "report_id" in value or "workflow_profile_id" in value


def _export_coverage_block(report: BenchmarkReport) -> dict[str, Any]:
    """Export pcs-core coverage block; omit harness-only aggregate dicts."""
    coverage = report.coverage or {}
    allowed = {
        "registry",
        "formal_checks",
        "scientific_memory",
        "release_reproducibility",
        "certificate_completeness",
        "explain_quality",
        "profile_coverage",
    }
    return {
        key: value
        for key, value in coverage.items()
        if key in allowed and _is_pcs_core_coverage_entry(value)
    }


def _build_pcs_summary(report: BenchmarkReport) -> dict[str, Any]:
    scores = _summary_scores(report)
    passed = sum(1 for r in report.runs if r.passed)
    failed = len(report.runs) - passed
    inner = report.summary

    summary: dict[str, Any] = {
        "total_cases": len(report.runs),
        "passed_cases": passed,
        "failed_cases": failed,
        "expected_failures_detected": sum(
            1 for r in report.runs if is_invalid_release_case_run(r) and r.passed
        ),
        "unexpected_passes": sum(1 for r in report.runs if r.passed and is_invalid_release_case_run(r)),
        "unexpected_failures": sum(
            1 for r in report.runs if not r.passed and is_valid_release_case_run(r)
        ),
        "failure_localization_accuracy": scores.get("failure_localization_accuracy", 0.0),
        "repair_hint_accuracy": scores.get("repair_hint_quality_score", 0.0),
        "formal_check_coverage": scores.get("formal_check_coverage_score", 0.0),
        "registry_coverage": scores.get("registry_coverage_score", 0.0),
        "scientific_memory_render_coverage": scores.get(
            "scientific_memory_interpretability_score", 0.0
        ),
        "execution_mode": inner.get("execution_mode", "simulate"),
        "evidence_grade": inner.get("evidence_grade", "developer"),
        "live_cases": int(inner.get("live_cases", 0)),
        "simulated_cases": int(inner.get("simulated_cases", 0)),
        "hybrid_fallback_cases": int(inner.get("hybrid_fallback_cases", 0)),
    }
    for key in (
        "release_reproducibility_score",
        "certificate_completeness_score",
        "registry_coverage_score",
        "formal_check_coverage_score",
        "scientific_memory_interpretability_score",
        "repair_hint_quality_score",
        "cross_domain_portability_score",
    ):
        value = scores.get(key)
        if value is not None:
            summary[key] = value
    return summary


def is_valid_release_case_run(run: BenchmarkRun) -> bool:
    from pcs_bench.benchmark_vocabulary import is_valid_release_case

    return is_valid_release_case(run.expected_status, run.expected_system_outcome)


def is_invalid_release_case_run(run: BenchmarkRun) -> bool:
    from pcs_bench.benchmark_vocabulary import is_invalid_release_case

    return is_invalid_release_case(run.expected_status, run.expected_system_outcome)


def _metric_summaries_export(summaries: list[MetricSummary]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in summaries:
        entry: dict[str, Any] = {
            "name": s.name,
            "applicability": s.applicability,
        }
        if s.score is not None:
            entry["score"] = round(s.score, 6)
        if s.reason:
            entry["reason"] = s.reason
        if s.numerator or s.denominator:
            entry["numerator"] = s.numerator
            entry["denominator"] = s.denominator
        out.append(entry)
    return out


def metrics_contract(pcs_core_path: Path | None = None) -> str:
    """Detect pcs-core BenchmarkReport metrics shape: metrics_array or metrics_object."""
    from pcs_bench.validation.schema_loader import load_artifact_schema

    root = pcs_core_path if pcs_core_path and (pcs_core_path / "schemas").is_dir() else _PKG_ROOT
    schema = load_artifact_schema(root, "BenchmarkReport.v0") or {}
    metrics_prop = schema.get("properties", {}).get("metrics", {})
    if metrics_prop.get("type") == "array":
        return "metrics_array"
    if metrics_prop.get("type") == "object":
        return "metrics_object"
    return "unknown"


def export_metrics_for_pcs_core(
    report: BenchmarkReport,
    pcs_core_path: Path | None = None,
    *,
    schema_version: str = "v0",
) -> dict[str, Any]:
    """Export metrics block matching the pcs-core BenchmarkReport schema (no silent invalid JSON)."""
    del schema_version  # v0 only today; reserved for future schema forks
    contract = metrics_contract(pcs_core_path)
    names = _metrics_name_list(report.metric_summaries)
    summaries = _metric_summaries_export(report.metric_summaries)

    if contract == "metrics_object":
        raise ValueError(
            "pcs-core BenchmarkReport.v0 expects metrics as an object in this checkout, "
            "but pcs-bench exports metrics as an array of benchmark_metric_id values. "
            "Upgrade pcs-core or sync schemas."
        )
    if contract not in ("metrics_array", "unknown"):
        raise ValueError(f"Unsupported metrics contract: {contract}")

    from pcs_bench.validation.schema_loader import load_artifact_schema

    root = pcs_core_path if pcs_core_path and (pcs_core_path / "schemas").is_dir() else _PKG_ROOT
    schema = load_artifact_schema(root, "BenchmarkReport.v0") or {}
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    block: dict[str, Any] = {"metrics": names or list(KNOWN_METRIC_IDS)}
    if "metric_summaries" in props or "metric_summaries" in required:
        block["metric_summaries"] = summaries
    return block


def _metrics_name_list(summaries: list[MetricSummary]) -> list[str]:
    names: list[str] = []
    for s in summaries:
        if s.name in KNOWN_METRIC_IDS and s.name not in names:
            names.append(s.name)
    return names or list(KNOWN_METRIC_IDS)


def _export_run_record(
    run: BenchmarkRun,
    runs_dir: Path,
    *,
    source_repo: str,
    source_commit: str,
) -> dict[str, Any]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    rel_dir = runs_dir / run.run_id
    rel_dir.mkdir(parents=True, exist_ok=True)
    run_path = rel_dir / f"benchmark_run.{run.case_id}.v0.json"
    bench_status = benchmark_status_for_run(run.passed)
    if bench_status not in ("passed", "failed", "skipped", "error"):
        bench_status = "passed" if run.passed else "failed"
    started = datetime.now(timezone.utc).isoformat()
    system_outcome = run.observed_system_outcome or ""
    if system_outcome in ("admitted", "rejected"):
        admission = system_outcome
    elif bench_status == "passed":
        admission = "admitted"
    else:
        admission = "rejected"

    run_doc: dict[str, Any] = {
        "schema_version": "v0",
        "run_id": run.run_id,
        "task_id": run.task_id or run.case_id,
        "case_id": run.case_id,
        "started_at": started,
        "completed_at": started,
        "commands": [
            {
                "command": " ".join(c.command) if isinstance(c.command, list) else str(c.command),
                "exit_code": c.exit_code,
            }
            for c in run.commands[:50]
        ],
        "artifacts_produced": [a for a in run.artifacts if a][:100],
        "observed_status": bench_status,
        "observed_failure_code": run.observed_failure_code,
        "observed_responsible_component": run.observed_responsible_component,
        "observed_repair_hint": run.observed_repair_hint,
        "system_admission_outcome": admission,
        "duration_ms": run.duration_ms,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "signature_or_digest": _run_digest(run),
    }
    run_path.write_text(json.dumps(run_doc, indent=2), encoding="utf-8")
    return {
        "run_id": run.run_id,
        "case_id": run.case_id,
        "path": str(run_path.as_posix()),
        "observed_status": bench_status,
    }


def _run_digest(run: BenchmarkRun) -> str:
    payload = json.dumps(
        {
            "run_id": run.run_id,
            "case_id": run.case_id,
            "passed": run.passed,
            "observed_system_outcome": run.observed_system_outcome,
        },
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _failures_export(report: BenchmarkReport) -> list[dict[str, str]]:
    if report.failures:
        return [{"case_id": f.case_id, "message": f.reason} for f in report.failures]
    return [
        {
            "case_id": run.case_id,
            "message": (
                f"expected benchmark={run.expected_status} system={run.expected_system_outcome}; "
                f"observed system={run.observed_system_outcome}"
            ),
        }
        for run in report.runs
        if not run.passed
    ]


def to_benchmark_report_v0_dict(
    report: BenchmarkReport,
    *,
    runs_output_dir: Path | None = None,
    pcs_core_path: Path | None = None,
) -> dict[str, Any]:
    """Canonical pcs-core BenchmarkReport.v0 JSON object."""
    report = enrich_report_for_export(report)
    runs_dir = runs_output_dir or Path("runs")
    source_commit = report.source_commit or pcs_bench_source_commit()
    metrics_block = export_metrics_for_pcs_core(report, pcs_core_path)

    return {
        "schema_version": "v0",
        "report_id": report.report_id,
        "benchmark_suite_id": report.benchmark_suite_id,
        "runs": [
            _export_run_record(
                run,
                runs_dir,
                source_repo=report.source_repo or PCS_BENCH_SOURCE_REPO,
                source_commit=source_commit,
            )
            for run in report.runs
        ],
        **metrics_block,
        "summary": _build_pcs_summary(report),
        "coverage": _export_coverage_block(report),
        "failures": _failures_export(report),
        "source_repo": report.source_repo,
        "source_commit": source_commit,
        "signature_or_digest": report.signature_or_digest,
        "producer_id": "pcs-bench",
    }


def validate_report_policy(data: dict) -> list[str]:
    """Semantic checks beyond JSON Schema."""
    errors: list[str] = []

    commit = data.get("source_commit", "")
    if commit in PLACEHOLDER_COMMITS or len(commit) != 40:
        errors.append(f"source_commit must be a 40-char git commit, got {commit!r}")

    digest = data.get("signature_or_digest", "")
    if not digest or not str(digest).startswith("sha256:") or len(str(digest)) != 71:
        errors.append("signature_or_digest must be sha256:<64 hex chars>")

    metrics = data.get("metrics")
    if isinstance(metrics, dict):
        errors.append(
            "metrics must be an array of benchmark_metric_id names, not an object "
            "(use metric_summaries for scores and applicability)"
        )
    elif isinstance(metrics, list):
        for name in metrics:
            if name not in KNOWN_METRIC_IDS:
                errors.append(f"Unrecognized metric name in metrics array: {name}")
    else:
        errors.append("metrics must be a non-empty array")

    for entry in data.get("metric_summaries", []):
        if entry.get("name") not in KNOWN_METRIC_IDS:
            errors.append(f"Unrecognized metric in metric_summaries: {entry.get('name')}")

    grade = data.get("summary", {}).get("evidence_grade")
    mode = data.get("summary", {}).get("execution_mode")
    if grade == "release" and mode != "live":
        errors.append("release evidence_grade requires execution_mode=live")
    if grade == "release" and int(data.get("summary", {}).get("live_cases", 0)) == 0:
        errors.append("release evidence_grade requires live_cases > 0")

    for run_ref in data.get("runs", []):
        path = run_ref.get("path")
        if path and not Path(path).exists():
            errors.append(f"Missing run artifact path: {path}")

    return errors


def validate_report_strict(
    report: BenchmarkReport | dict[str, Any],
    config,
    *,
    schema_source: Path | None = None,
    runs_output_dir: Path | None = None,
) -> list[str]:
    if isinstance(report, BenchmarkReport):
        data = to_benchmark_report_v0_dict(report, runs_output_dir=runs_output_dir)
    else:
        data = report

    pcs_core = schema_source or config.repos.pcs_core
    from pcs_bench.validation.schema_loader import validate_instance

    errors = validate_instance(data, "BenchmarkReport.v0", pcs_core)
    errors.extend(validate_report_policy(data))
    return errors
