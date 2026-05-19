"""JSON report passthrough."""

from __future__ import annotations

import json

from pcs_bench.schemas import BenchmarkReport


def render_json(report: BenchmarkReport) -> str:
    return json.dumps(report.model_dump(), indent=2, default=str)
