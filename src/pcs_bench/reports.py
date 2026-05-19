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
    report.finalize(digest=report_digest(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)
    return path


def load_report(path: Path) -> BenchmarkReport:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return BenchmarkReport.model_validate(data)
