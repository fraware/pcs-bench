#!/usr/bin/env python3
"""Write pcs-core-conformant benchmark_case.v0.json fixtures."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcs_bench.benchmark_vocabulary import (  # noqa: E402
    BENCHMARK_FAILED,
    BENCHMARK_PASSED,
    CASE_KIND_BY_KEY,
    REPAIR_HINT_MAP,
    RESPONSIBLE_COMPONENT_MAP,
    SYSTEM_ADMITTED,
    SYSTEM_FORMAL_FAILED,
    SYSTEM_IMPORT_FAILED,
    SYSTEM_REJECTED,
    SYSTEM_RENDER_FAILED,
    SYSTEM_STALE,
)
from pcs_bench.report_export import fixture_source_commit  # noqa: E402

PCS_BENCH_REPO = "https://github.com/fraware/pcs-bench"


def case_digest(case_id: str) -> str:
    return f"sha256:{hashlib.sha256(case_id.encode()).hexdigest()}"


def system_outcome_for_failure_code(code: str) -> str:
    code_l = code.lower()
    if "stale" in code_l:
        return SYSTEM_STALE
    if "import" in code_l:
        return SYSTEM_IMPORT_FAILED
    if "render" in code_l:
        return SYSTEM_RENDER_FAILED
    if "lean" in code_l or "formal" in code_l or "theorem" in code_l:
        return SYSTEM_FORMAL_FAILED
    return SYSTEM_REJECTED


def write_case_json(
    case_dir: Path,
    *,
    case_id: str,
    task_id: str,
    workflow_id: str,
    case_kind: str,
    benchmark_status: str,
    system_outcome: str,
    expected_failure_code: str = "",
    expected_responsible_component: str = "unknown",
    expected_repair_hint_kind: str = "none",
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    kind = CASE_KIND_BY_KEY.get(case_kind, case_kind)
    component = RESPONSIBLE_COMPONENT_MAP.get(
        expected_responsible_component, expected_responsible_component
    )
    repair = REPAIR_HINT_MAP.get(expected_repair_hint_kind, expected_repair_hint_kind)
    payload = {
        "schema_version": "v0",
        "case_id": case_id,
        "task_id": task_id,
        "workflow_id": workflow_id,
        "case_kind": kind,
        "input_artifacts": {"release_directory": "input_artifacts/"},
        "expected_status": benchmark_status,
        "expected_system_outcome": system_outcome,
        "expected_failure_code": expected_failure_code,
        "expected_responsible_component": component,
        "expected_repair_hint_kind": repair,
        "source_repo": PCS_BENCH_REPO,
        "source_commit": fixture_source_commit(),
        "signature_or_digest": case_digest(case_id),
    }
    (case_dir / "benchmark_case.v0.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def write_from_verification(
    case_dir: Path,
    *,
    case_id: str,
    task_id: str,
    workflow_id: str,
    case_kind: str,
    verification: dict,
) -> None:
    code = verification.get("failure_code", "")
    write_case_json(
        case_dir,
        case_id=case_id,
        task_id=task_id,
        workflow_id=workflow_id,
        case_kind=case_kind,
        benchmark_status=BENCHMARK_FAILED,
        system_outcome=system_outcome_for_failure_code(code),
        expected_failure_code=code,
        expected_responsible_component=verification.get("responsible_component", "unknown"),
        expected_repair_hint_kind=verification.get("repair_hint_kind", "unknown"),
    )


def write_valid_case(
    case_dir: Path,
    *,
    case_id: str,
    task_id: str,
    workflow_id: str,
    case_kind: str = "valid",
) -> None:
    write_case_json(
        case_dir,
        case_id=case_id,
        task_id=task_id,
        workflow_id=workflow_id,
        case_kind=case_kind,
        benchmark_status=BENCHMARK_PASSED,
        system_outcome=SYSTEM_ADMITTED,
        expected_failure_code="",
        expected_responsible_component="unknown",
        expected_repair_hint_kind="none",
    )
