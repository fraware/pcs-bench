"""Load pcs-core JSON Schema with local $ref resolution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_PKG_ROOT = Path(__file__).resolve().parent.parent
_EMBEDDED_DIR = _PKG_ROOT / "schemas" / "json"

_ARTIFACT_SCHEMA_FILES: dict[str, list[str]] = {
    "BenchmarkReport.v0": [
        "BenchmarkReport.v0.schema.json",
        "common.defs.json",
        "MetricSummary.v0.schema.json",
        "CoverageReport.v0.schema.json",
        "ExplainQualityReport.v0.schema.json",
        "ProfileCoverageReport.v0.schema.json",
    ],
    "BenchmarkCase.v0": [
        "BenchmarkCase.v0.schema.json",
        "common.defs.json",
    ],
    "common.defs": [
        "common.defs.json",
    ],
    "PcsBenchIngest.v0": [
        "PcsBenchIngest.v0.schema.json",
        "PcsBenchIngest.v0.json",
        "BenchmarkRun.v0.schema.json",
        "FailureLocalizationResult.v0.schema.json",
        "BenchmarkArtifactRef.v0.schema.json",
        "common.defs.json",
        "CoverageReport.v0.schema.json",
        "ExplainQualityReport.v0.schema.json",
        "ProfileCoverageReport.v0.schema.json",
    ],
    "BenchmarkRun.v0": [
        "BenchmarkRun.v0.schema.json",
        "common.defs.json",
    ],
    "FailureLocalizationResult.v0": [
        "FailureLocalizationResult.v0.schema.json",
        "common.defs.json",
    ],
    "BenchmarkArtifactRef.v0": [
        "BenchmarkArtifactRef.v0.schema.json",
        "common.defs.json",
    ],
    "CoverageReport.v0": [
        "CoverageReport.v0.schema.json",
        "common.defs.json",
    ],
    "ExplainQualityReport.v0": [
        "ExplainQualityReport.v0.schema.json",
        "common.defs.json",
    ],
    "ProfileCoverageReport.v0": [
        "ProfileCoverageReport.v0.schema.json",
        "common.defs.json",
    ],
}


def _embedded_schema_path(schema_name: str) -> Path:
    return _EMBEDDED_DIR / f"{schema_name}.json"


def _find_schema_file(pcs_core: Path, filename: str) -> Path | None:
    schemas_dir = pcs_core / "schemas"
    if schemas_dir.is_dir():
        candidate = schemas_dir / filename
        if candidate.exists():
            return candidate
    for name in (
        filename,
        filename.replace(".v0.schema.json", ".v0.json"),
        filename.replace(".schema.json", ".json"),
    ):
        embedded = _EMBEDDED_DIR / name
        if embedded.exists():
            return embedded
    return None


def _uses_legacy_metric_summary_ref(schema: dict) -> bool:
    from pcs_bench.schema_sync import uses_legacy_metric_summary_ref

    return uses_legacy_metric_summary_ref(schema)


def load_artifact_schema(pcs_core_path: Path, artifact_name: str) -> dict | None:
    """Load BenchmarkCase.v0.schema.json style artifact schema."""
    if artifact_name == "BenchmarkReport.v0":
        embedded = _embedded_schema_path(artifact_name)
        if embedded.is_file():
            return json.loads(embedded.read_text(encoding="utf-8"))
    candidates = _ARTIFACT_SCHEMA_FILES.get(
        artifact_name, [f"{artifact_name}.schema.json", f"{artifact_name}.json"]
    )
    primary = candidates[0]
    if artifact_name == "PcsBenchIngest.v0":
        for name in ("PcsBenchIngest.v0.json", "PcsBenchIngest.v0.schema.json"):
            if _find_schema_file(pcs_core_path, name) or (_EMBEDDED_DIR / name).exists():
                primary = name
                break
    path = _find_schema_file(pcs_core_path, primary)
    if not path:
        fallback = _embedded_schema_path(artifact_name)
        if fallback.exists():
            path = fallback
    if not path:
        return None
    schema = json.loads(path.read_text(encoding="utf-8"))
    if artifact_name == "BenchmarkReport.v0" and _uses_legacy_metric_summary_ref(schema):
        embedded = _embedded_schema_path(artifact_name)
        if embedded.exists():
            return json.loads(embedded.read_text(encoding="utf-8"))
    return schema


@lru_cache(maxsize=16)
def _registry_for(pcs_core_key: str, artifact_name: str) -> Registry:
    pcs_core = Path(pcs_core_key)
    registry = Registry()
    for filename in _ARTIFACT_SCHEMA_FILES.get(artifact_name, []):
        path = _find_schema_file(pcs_core, filename)
        if not path:
            continue
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource)
        uri = contents.get("$id")
        if uri:
            registry = registry.with_resource(uri, resource)
    return registry


def _load_common_def_schema(pcs_core_path: Path, def_name: str) -> dict | None:
    path = _find_schema_file(pcs_core_path, "common.defs.json")
    if not path:
        return None
    common = json.loads(path.read_text(encoding="utf-8"))
    sub = common.get("$defs", {}).get(def_name)
    if not sub:
        return None
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://pcs.sentinelops.ci/schemas/{def_name}",
        **sub,
    }


def validate_instance(
    instance: dict,
    artifact_name: str,
    pcs_core_path: Path,
) -> list[str]:
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema package required"]

    if artifact_name == "benchmark_command_entry":
        schema = _load_common_def_schema(pcs_core_path, "benchmark_command_entry")
        registry_key = "common.defs"
    else:
        schema = load_artifact_schema(pcs_core_path, artifact_name)
        registry_key = artifact_name
    if not schema:
        return [f"Schema not found for {artifact_name}"]

    root = pcs_core_path.resolve()
    if not (root / "schemas").is_dir():
        root = _PKG_ROOT
    registry = _registry_for(str(root), registry_key)
    if artifact_name == "benchmark_command_entry":
        defs_path = _find_schema_file(root, "common.defs.json")
        if defs_path:
            common = json.loads(defs_path.read_text(encoding="utf-8"))
            resource = Resource.from_contents(common, default_specification=DRAFT202012)
            registry = registry.with_resource(defs_path.name, resource)
    try:
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(instance)
        return []
    except jsonschema.ValidationError as exc:
        return [exc.message]
    except Exception as exc:
        return [f"schema validation error: {exc}"]
