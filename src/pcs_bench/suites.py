"""Benchmark suite loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from pcs_bench.cases import load_case, resolve_case_path
from pcs_bench.errors import SuiteNotFoundError
from pcs_bench.schemas import BenchmarkCase, BenchmarkSuite


def load_suite(suite_dir: Path) -> BenchmarkSuite:
    suite_yaml = suite_dir / "suite.yaml"
    if not suite_yaml.exists():
        raise SuiteNotFoundError(f"Suite not found: {suite_dir} (missing suite.yaml)")
    with suite_yaml.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return BenchmarkSuite.model_validate(raw)


def load_suite_cases(suite_dir: Path, suite: BenchmarkSuite) -> list[tuple[str, Path, BenchmarkCase]]:
    loaded: list[tuple[str, Path, BenchmarkCase]] = []
    for ref in suite.cases:
        case_path = resolve_case_path(suite_dir, ref.path)
        case = load_case(case_path)
        loaded.append((ref.case_id, case_path, case))
    return loaded
