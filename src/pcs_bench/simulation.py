"""Fixture-driven simulation when ecosystem CLIs are unavailable."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pcs_bench.benchmark_vocabulary import (
    SYSTEM_ADMITTED,
    SYSTEM_REJECTED,
    system_outcome_from_sidecar,
)
from pcs_bench.schemas import BenchmarkCase


@dataclass
class SimulatedOutcome:
    status: str
    system_outcome: str | None = None
    failure_code: str | None = None
    responsible_component: str | None = None
    repair_hint: str | None = None
    repair_hint_kind: str | None = None
    verification: dict[str, Any] | None = None
    rendered_sections: list[str] | None = None
    source: str = "case_expectation"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def find_case_root(suite_dir: Path, case: BenchmarkCase) -> Path | None:
    for ref_path in suite_dir.rglob("benchmark_case.v0.json"):
        try:
            with ref_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if data.get("case_id") == case.case_id:
                return ref_path.parent
        except (json.JSONDecodeError, OSError):
            continue
    return None


def load_expected_sidecar(case_root: Path, name: str) -> dict[str, Any]:
    expected = case_root / "expected" / name
    return _load_json(expected)


def simulate_outcome(case: BenchmarkCase, suite_dir: Path) -> SimulatedOutcome:
    case_root = find_case_root(suite_dir, case)
    if case_root:
        verification = load_expected_sidecar(case_root, "verification_result.json")
        if verification:
            return SimulatedOutcome(
                status=verification.get("status") or case.expected_system_outcome or "",
                system_outcome=system_outcome_from_sidecar(verification),
                failure_code=verification.get("failure_code") or case.expected_failure_code,
                responsible_component=verification.get("responsible_component")
                or case.expected_responsible_component,
                repair_hint=_stringify_hint(verification.get("repair_hint")),
                repair_hint_kind=verification.get("repair_hint_kind")
                or case.expected_repair_hint_kind,
                verification=verification,
                rendered_sections=_load_rendered_sections(case_root),
                source="expected_sidecar",
            )

    return SimulatedOutcome(
        status=case.expected_system_outcome or SYSTEM_REJECTED,
        system_outcome=case.expected_system_outcome
        or (SYSTEM_ADMITTED if case.expected_status == "passed" else SYSTEM_REJECTED),
        failure_code=case.expected_failure_code,
        responsible_component=case.expected_responsible_component,
        repair_hint_kind=case.expected_repair_hint_kind,
        repair_hint=_default_repair_hint(case),
        source="case_expectation",
    )


def _load_rendered_sections(case_root: Path) -> list[str] | None:
    data = load_expected_sidecar(case_root, "rendered_sections.json")
    sections = data.get("sections") or data.get("rendered_sections")
    return sections if isinstance(sections, list) else None


def _stringify_hint(hint: Any) -> str | None:
    if hint is None:
        return None
    if isinstance(hint, str):
        return hint
    if isinstance(hint, dict):
        return json.dumps(hint, sort_keys=True)
    return str(hint)


def _default_repair_hint(case: BenchmarkCase) -> str | None:
    if case.expected_status == "passed":
        return None
    kind = case.expected_repair_hint_kind or "unspecified_repair"
    component = case.expected_responsible_component or "unknown"
    code = case.expected_failure_code or "unknown_failure"
    return (
        f"responsible_component={component}; failure_code={code}; "
        f"repair_kind={kind}; action=see benchmark case documentation"
    )
