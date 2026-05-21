"""Sync JSON schemas from pcs-core into pcs-bench embedded fallbacks."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Harness export uses {name, applicability, score}; pcs-core may still ship MetricSummary.v0 refs.
_INLINE_METRIC_SUMMARY = {
    "metric_summary": {
        "type": "object",
        "required": ["name", "applicability"],
        "additionalProperties": False,
        "properties": {
            "name": {"$ref": "common.defs.json#/$defs/benchmark_metric_id"},
            "score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "applicability": {
                "$ref": "common.defs.json#/$defs/benchmark_metric_applicability"
            },
            "reason": {"type": "string"},
            "numerator": {"type": "integer", "minimum": 0},
            "denominator": {"type": "integer", "minimum": 0},
        },
    }
}

SCHEMA_NAMES = (
    "BenchmarkReport.v0",
    "BenchmarkCase.v0",
    "BenchmarkSuite.v0",
    "FailureLocalization.v0",
)

# Copied by filename (not Benchmark*.v0 naming) for $ref resolution offline.
AUX_SCHEMA_FILES = (
    "common.defs.json",
    "CoverageReport.v0.schema.json",
    "ExplainQualityReport.v0.schema.json",
    "ProfileCoverageReport.v0.schema.json",
)


@dataclass
class SchemaSyncResult:
    copied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _schema_candidates(pcs_core_path: Path, name: str) -> list[Path]:
    return [
        pcs_core_path / "schemas" / f"{name}.schema.json",
        pcs_core_path / "schemas" / f"{name}.json",
        pcs_core_path / "schema" / f"{name}.json",
        pcs_core_path / "src" / "schemas" / f"{name}.json",
    ]


def embedded_schema_dir() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "json"


def uses_legacy_metric_summary_ref(schema: dict) -> bool:
    items = schema.get("properties", {}).get("metric_summaries", {}).get("items", {})
    return "MetricSummary.v0.schema.json" in str(items.get("$ref", ""))


def ensure_benchmark_report_metric_summary_inline(path: Path) -> bool:
    """Replace MetricSummary.v0 ref with inline metric_summary for harness export shape."""
    if not path.exists():
        return False
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not uses_legacy_metric_summary_ref(schema):
        return False
    schema["properties"]["metric_summaries"]["items"] = {"$ref": "#/$defs/metric_summary"}
    schema.setdefault("$defs", {}).update(_INLINE_METRIC_SUMMARY)
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return True


def sync_schemas_from_pcs_core(
    pcs_core_path: Path,
    *,
    dest_dir: Path | None = None,
) -> SchemaSyncResult:
    """Copy known pcs-core schemas into pcs_bench/schemas/json/."""
    result = SchemaSyncResult()
    pcs_core_path = pcs_core_path.resolve()
    if not pcs_core_path.is_dir():
        result.errors.append(f"pcs-core path not found: {pcs_core_path}")
        return result

    dest_dir = dest_dir or embedded_schema_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    for name in SCHEMA_NAMES:
        source: Path | None = None
        for candidate in _schema_candidates(pcs_core_path, name):
            if candidate.exists():
                source = candidate
                break
        if not source:
            result.missing.append(name)
            continue
        target = dest_dir / f"{name}.json"
        shutil.copy2(source, target)
        result.copied.append(name)

    for filename in AUX_SCHEMA_FILES:
        source = pcs_core_path / "schemas" / filename
        if not source.exists():
            result.missing.append(filename)
            continue
        shutil.copy2(source, dest_dir / filename)
        result.copied.append(filename)

    report_path = dest_dir / "BenchmarkReport.v0.json"
    if ensure_benchmark_report_metric_summary_inline(report_path):
        result.copied.append("BenchmarkReport.v0.inline_metric_summary")

    pcs_report = pcs_core_path / "schemas" / "BenchmarkReport.v0.schema.json"
    ensure_benchmark_report_metric_summary_inline(pcs_report)

    return result
