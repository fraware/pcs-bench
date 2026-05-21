"""Shared builders for producer ingest test fixtures."""

from __future__ import annotations

from typing import Any

COMMIT = "bb5d083dff2bb1060e88a5e643b46c0894947e05"
DIGEST = "sha256:127063f201d0da5c80a8670668f9ccdd9d4ea5cead95d8a0fae6e716fecb5c57"
TS = "2026-05-21T12:00:00+00:00"
TS_END = "2026-05-21T12:00:01+00:00"


def benchmark_run(
    *,
    run_id: str,
    case_id: str,
    suite_id: str,
    passed: bool = True,
    expected_status: str = "passed",
    system_outcome: str = "admitted",
    source_repo: str,
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "run_id": run_id,
        "case_id": case_id,
        "suite_id": suite_id,
        "task_id": f"{case_id}-task",
        "workflow_id": "pcs.benchmark",
        "expected_status": expected_status,
        "expected_system_outcome": system_outcome,
        "expected_failure_code": "",
        "benchmark_passed": passed,
        "started_at": TS,
        "completed_at": TS_END,
        "observed_status": expected_status,
        "observed_system_outcome": system_outcome,
        "observed_failure_code": "",
        "observed_responsible_component": "unknown",
        "observed_repair_hint": "unknown",
        "execution_kind": "live",
        "source_repo": source_repo,
        "source_commit": COMMIT,
        "signature_or_digest": DIGEST,
    }


def coverage_report(*, coverage_id: str, metric: str, source_repo: str) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "coverage_id": coverage_id,
        "metric": metric,
        "numerator": 1,
        "denominator": 1,
        "coverage_ratio": 1.0,
        "details": {},
        "source_repo": source_repo,
        "source_commit": COMMIT,
        "signature_or_digest": DIGEST,
    }


def explain_quality_report(*, case_id: str, suite_id: str, producer_id: str) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "report_id": f"explain-{case_id}",
        "suite_id": suite_id,
        "case_id": case_id,
        "producer_id": producer_id,
        "required_sections": ["provenance", "verification", "limitations"],
        "sections": {
            "provenance": {"present": True, "score": 1.0},
            "verification": {"present": True, "score": 1.0},
            "limitations": {"present": True, "score": 1.0},
        },
        "sections_present_count": 3,
        "sections_required_count": 3,
        "quality_score": 1.0,
        "gaps": [],
        "source_repo": "https://github.com/fraware/pcs-bench",
        "source_commit": COMMIT,
        "signature_or_digest": DIGEST,
    }


def ingest_document(
    *,
    producer_id: str,
    suite_id: str,
    source_repo: str,
    runs: list[dict[str, Any]],
    coverage_reports: list[dict[str, Any]] | None = None,
    explain_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "producer_id": producer_id,
        "benchmark_suite_id": suite_id,
        "source_repo": source_repo,
        "source_commit": COMMIT,
        "signature_or_digest": DIGEST,
        "benchmark_runs": runs,
        "coverage_reports": coverage_reports or [],
        "explain_quality_reports": explain_reports or [],
        "profile_coverage_reports": [],
        "commands": [
            {"command": "producer benchmark", "exit_code": 0},
        ],
        "metrics": ["release_reproducibility_score"],
        "metric_summaries": [
            {
                "name": "release_reproducibility_score",
                "score": 1.0,
                "applicability": "measured",
            }
        ],
        "attachments": [
            {
                "attachment_id": "native-summary",
                "role": "producer_native",
                "media_type": "application/json",
                "content": {"producer": producer_id, "suite_id": suite_id},
            }
        ],
    }
