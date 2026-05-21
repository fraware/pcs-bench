"""Benchmark report persistence and loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pcs_bench.schemas import BenchmarkReport, BenchmarkRun


def report_digest(report: BenchmarkReport) -> str:
    payload = report.model_dump(exclude={"signature_or_digest", "completed_at"})
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"sha256:{digest}"


def save_report(
    report: BenchmarkReport,
    path: Path,
    *,
    pcs_core_path: Path | None = None,
) -> Path:
    from pcs_bench.report_export import to_benchmark_report_v0_dict

    report.finalize(digest=report_digest(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    runs_dir = path.parent / f"{path.stem}-runs"
    payload = to_benchmark_report_v0_dict(
        report, runs_output_dir=runs_dir, pcs_core_path=pcs_core_path
    )
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def _expectation_matched(
    *,
    expected_status: str,
    expected_system_outcome: str | None,
    expected_failure_code: str | None,
    expected_responsible_component: str | None,
    observed_system_outcome: str,
    observed_failure_code: str | None,
    observed_responsible_component: str | None,
) -> bool:
    from pcs_bench.benchmark_vocabulary import (
        is_invalid_release_case,
        is_valid_release_case,
    )

    if is_valid_release_case(expected_status, expected_system_outcome):
        return observed_system_outcome == (expected_system_outcome or "admitted")
    if is_invalid_release_case(expected_status, expected_system_outcome):
        code_ok = not expected_failure_code or observed_failure_code == expected_failure_code
        component_ok = (
            not expected_responsible_component
            or observed_responsible_component == expected_responsible_component
        )
        return code_ok and component_ok
    return observed_system_outcome == expected_system_outcome


def _case_expectations(case_id: str, benchmarks_root: Path) -> dict[str, str | None]:
    for case_file in benchmarks_root.rglob("benchmark_case.v0.json"):
        try:
            doc = json.loads(case_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if doc.get("case_id") == case_id:
            return {
                "expected_status": doc.get("expected_status", "passed"),
                "expected_system_outcome": doc.get("expected_system_outcome"),
                "expected_failure_code": doc.get("expected_failure_code") or None,
                "expected_responsible_component": doc.get("expected_responsible_component"),
            }
    return {
        "expected_status": "passed",
        "expected_system_outcome": None,
        "expected_failure_code": None,
        "expected_responsible_component": None,
    }


def _run_from_ref(ref: dict, report_path: Path, *, benchmarks_root: Path) -> BenchmarkRun:
    run_path = Path(ref["path"])
    if not run_path.is_absolute():
        run_path = (report_path.parent / run_path).resolve()
    suite_id = ref.get("suite_id", "unknown")
    expectations = _case_expectations(ref["case_id"], benchmarks_root)
    if run_path.exists():
        doc = json.loads(run_path.read_text(encoding="utf-8"))
        suite_id = doc.get("suite_id", ref.get("suite_id", suite_id))
        expectations = {
            "expected_status": doc.get("expected_status", expectations["expected_status"]),
            "expected_system_outcome": doc.get(
                "expected_system_outcome", expectations["expected_system_outcome"]
            ),
            "expected_failure_code": doc.get("expected_failure_code")
            or expectations["expected_failure_code"],
            "expected_responsible_component": doc.get("expected_responsible_component")
            or expectations["expected_responsible_component"],
        }
        observed_status = doc.get("observed_status", ref.get("observed_status", "passed"))
        if "benchmark_passed" in doc:
            passed = bool(doc["benchmark_passed"])
        else:
            passed = _expectation_matched(
                expected_status=str(expectations["expected_status"]),
                expected_system_outcome=expectations["expected_system_outcome"],
                expected_failure_code=expectations["expected_failure_code"],
                expected_responsible_component=expectations["expected_responsible_component"],
                observed_system_outcome=doc.get("observed_system_outcome") or "",
                observed_failure_code=doc.get("observed_failure_code"),
                observed_responsible_component=doc.get("observed_responsible_component"),
            )
        return BenchmarkRun(
            run_id=doc.get("run_id", ref["run_id"]),
            case_id=doc.get("case_id", ref["case_id"]),
            suite_id=suite_id,
            task_id=doc.get("task_id"),
            observed_status=observed_status,
            expected_status=str(expectations["expected_status"]),
            expected_system_outcome=expectations["expected_system_outcome"],
            expected_failure_code=expectations["expected_failure_code"],
            observed_system_outcome=doc.get("observed_system_outcome"),
            passed=passed,
            observed_failure_code=doc.get("observed_failure_code"),
            observed_responsible_component=doc.get("observed_responsible_component"),
            observed_repair_hint=doc.get("observed_repair_hint"),
            duration_ms=int(doc.get("duration_ms", 0)),
        )
    status = ref.get("observed_status", "passed")
    return BenchmarkRun(
        run_id=ref["run_id"],
        case_id=ref["case_id"],
        suite_id=suite_id,
        observed_status=status,
        expected_status=str(expectations["expected_status"]),
        expected_system_outcome=expectations["expected_system_outcome"],
        expected_failure_code=expectations["expected_failure_code"],
        passed=status == expectations["expected_status"],
    )


def _normalize_failures(
    raw_failures: list[dict],
    runs: list[dict],
) -> list[dict]:
    run_by_case = {r.get("case_id"): r for r in runs if r.get("case_id")}
    normalized: list[dict] = []
    for entry in raw_failures:
        if "reason" in entry and "suite_id" in entry:
            normalized.append(entry)
            continue
        case_id = entry.get("case_id", "")
        run = run_by_case.get(case_id, {})
        normalized.append(
            {
                "case_id": case_id,
                "suite_id": entry.get("suite_id") or run.get("suite_id", "unknown"),
                "reason": entry.get("reason") or entry.get("message", ""),
                "responsible_repo": entry.get("responsible_repo"),
                "responsible_component": entry.get("responsible_component"),
                "repair_hint": entry.get("repair_hint"),
                "logs_path": entry.get("logs_path"),
                "artifacts_path": entry.get("artifacts_path"),
            }
        )
    return normalized


def load_report(path: Path) -> BenchmarkReport:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    benchmarks_root = Path("benchmarks")
    runs_raw = data.get("runs") or []
    if runs_raw and "expected_status" not in runs_raw[0]:
        data["runs"] = [
            _run_from_ref(ref, path, benchmarks_root=benchmarks_root).model_dump()
            for ref in runs_raw
        ]

    if data.get("failures"):
        data["failures"] = _normalize_failures(data["failures"], data.get("runs") or [])

    if isinstance(data.get("metrics"), list) and not data.get("metric_summaries"):
        data["metric_summaries"] = [
            {"name": name, "applicability": "measured"} for name in data["metrics"]
        ]
    elif isinstance(data.get("metrics"), dict):
        raw_metrics = data["metrics"]
        summaries: list[dict] = []
        names: list[str] = []
        for name, value in raw_metrics.items():
            if isinstance(value, dict):
                summaries.append(
                    {
                        "name": name,
                        "score": value.get("score"),
                        "applicability": value.get("applicability", "measured"),
                        "reason": value.get("reason"),
                    }
                )
                if value.get("applicability") == "measured":
                    names.append(name)
            elif value is not None:
                summaries.append(
                    {"name": name, "score": float(value), "applicability": "measured"}
                )
                names.append(name)
        data["metrics"] = names
        data["metric_summaries"] = summaries

    return BenchmarkReport.model_validate(data)
