"""Benchmark report persistence and loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pcs_bench.schemas import BenchmarkReport


def report_digest(report: BenchmarkReport) -> str:
    payload = report.model_dump(exclude={"signature_or_digest", "completed_at"})
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"sha256:{digest}"


def save_report(report: BenchmarkReport, path: Path) -> Path:
    from pcs_bench.report_export import to_benchmark_report_v0_dict

    report.finalize(digest=report_digest(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_benchmark_report_v0_dict(report)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def load_report(path: Path) -> BenchmarkReport:
    from pcs_bench.schemas import MetricSummary

    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    raw_metrics = data.get("metrics") or {}
    if raw_metrics and not data.get("metric_summaries"):
        summaries: list[dict] = []
        flat: dict[str, float] = {}
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
                if value.get("applicability") == "measured" and value.get("score") is not None:
                    flat[name] = float(value["score"])
            elif value is not None:
                flat[name] = float(value)
                summaries.append(
                    {"name": name, "score": float(value), "applicability": "measured"}
                )
        data["metrics"] = flat
        data["metric_summaries"] = summaries
    return BenchmarkReport.model_validate(data)
