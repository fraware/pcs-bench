#!/usr/bin/env python3
"""Rewrite every benchmark_case.v0.json to pcs-core vocabulary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from pcs_bench.benchmark_vocabulary import normalize_legacy_case_payload  # noqa: E402
from case_fixture_writer import (  # noqa: E402
    write_from_verification,
    write_valid_case,
    system_outcome_for_failure_code,
)
from pcs_bench.benchmark_vocabulary import (  # noqa: E402
    BENCHMARK_FAILED,
    BENCHMARK_PASSED,
    SYSTEM_ADMITTED,
)


def main() -> None:
    for path in sorted((ROOT / "benchmarks").rglob("benchmark_case.v0.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        normalized = normalize_legacy_case_payload(data)
        case_dir = path.parent
        case_id = normalized["case_id"]
        task_id = normalized["task_id"]
        workflow_id = normalized["workflow_id"]
        kind = normalized["case_kind"]
        bench = normalized["expected_status"]
        system = normalized.get("expected_system_outcome") or SYSTEM_ADMITTED
        if bench == BENCHMARK_PASSED:
            write_valid_case(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=workflow_id,
                case_kind=kind,
            )
        else:
            from case_fixture_writer import write_case_json

            write_case_json(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=workflow_id,
                case_kind=kind,
                benchmark_status=BENCHMARK_FAILED,
                system_outcome=system,
                expected_failure_code=normalized.get("expected_failure_code", ""),
                expected_responsible_component=normalized.get(
                    "expected_responsible_component", "unknown"
                ),
                expected_repair_hint_kind=normalized.get("expected_repair_hint_kind", "unknown"),
            )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
