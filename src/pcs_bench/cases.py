"""Benchmark case loading."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.benchmark_vocabulary import normalize_legacy_case_payload
from pcs_bench.errors import CaseNotFoundError
from pcs_bench.schemas import BenchmarkCase


def load_case(path: Path) -> BenchmarkCase:
    if not path.exists():
        raise CaseNotFoundError(f"Case file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    data = normalize_legacy_case_payload(data)
    return BenchmarkCase.model_validate(data)


def resolve_case_path(suite_dir: Path, case_ref_path: str) -> Path:
    return (suite_dir / case_ref_path).resolve()


def case_input_dir(case_workspace: Path, case: BenchmarkCase) -> Path:
    """Resolve input artifacts directory within case workspace."""
    rel = (
        case.input_artifacts.get("release_directory")
        or case.input_artifacts.get("release_dir")
        or "input_artifacts/"
    )
    primary = (case_workspace / "input" / rel.strip("/")).resolve()
    if primary.exists():
        return primary
    # Fallback for legacy staging layout
    legacy = (case_workspace / "input" / "release_dir").resolve()
    if legacy.exists():
        return legacy
    return (case_workspace / "input").resolve()
