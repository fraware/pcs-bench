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


def save_report(report: BenchmarkReport, path: Path) -> Path:
    from pcs_bench.report_export import to_benchmark_report_v0_dict

    report.finalize(digest=report_digest(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    runs_dir = path.parent / f"{path.stem}-runs"
    payload = to_benchmark_report_v0_dict(report, runs_output_dir=runs_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def _run_from_ref(ref: dict, report_path: Path) -> BenchmarkRun:
    run_path = Path(ref["path"])
    if not run_path.is_absolute():
        run_path = (report_path.parent / run_path).resolve()
    if run_path.exists():
        doc = json.loads(run_path.read_text(encoding="utf-8"))
        return BenchmarkRun(
            run_id=doc.get("run_id", ref["run_id"]),
            case_id=doc.get("case_id", ref["case_id"]),
            suite_id=ref.get("suite_id", "unknown"),
            task_id=doc.get("task_id"),
            observed_status=doc.get("observed_status", ref.get("observed_status", "passed")),
            expected_status="passed",
            observed_system_outcome=doc.get("observed_system_outcome"),
            passed=doc.get("observed_status") == "passed",
            observed_failure_code=doc.get("observed_failure_code"),
            observed_responsible_component=doc.get("observed_responsible_component"),
            observed_repair_hint=doc.get("observed_repair_hint"),
            duration_ms=int(doc.get("duration_ms", 0)),
        )
    status = ref.get("observed_status", "passed")
    return BenchmarkRun(
        run_id=ref["run_id"],
        case_id=ref["case_id"],
        suite_id=ref.get("suite_id", "unknown"),
        observed_status=status,
        expected_status="passed",
        passed=status == "passed",
    )


def load_report(path: Path) -> BenchmarkReport:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    runs_raw = data.get("runs") or []
    if runs_raw and "expected_status" not in runs_raw[0]:
        data["runs"] = [_run_from_ref(ref, path).model_dump() for ref in runs_raw]

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
