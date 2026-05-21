"""Tests for pcs-core schema sync."""

from pathlib import Path

from pcs_bench.schema_sync import embedded_schema_dir, sync_schemas_from_pcs_core


def test_sync_from_embedded_pcs_bench_schemas(tmp_path: Path) -> None:
    """Sync uses pcs-core layout; fall back gracefully when path missing."""
    missing = sync_schemas_from_pcs_core(tmp_path / "no-such-repo")
    assert missing.errors

    # Embedded dir always has BenchmarkReport after package install
    assert (embedded_schema_dir() / "BenchmarkReport.v0.json").exists()


def test_sync_copies_when_pcs_core_present(tmp_path: Path) -> None:
    src = tmp_path / "pcs-core" / "schemas"
    src.mkdir(parents=True)
    dest = tmp_path / "out"
    schema = {"title": "BenchmarkReport.v0", "type": "object"}
    import json

    (src / "BenchmarkReport.v0.json").write_text(json.dumps(schema), encoding="utf-8")
    result = sync_schemas_from_pcs_core(tmp_path / "pcs-core", dest_dir=dest)
    assert "BenchmarkReport.v0" in result.copied
    assert (dest / "BenchmarkReport.v0.json").read_text(encoding="utf-8") == json.dumps(schema)


def test_sync_inlines_legacy_metric_summary_ref(tmp_path: Path) -> None:
    import json

    from pcs_bench.schema_sync import uses_legacy_metric_summary_ref

    src = tmp_path / "pcs-core" / "schemas"
    src.mkdir(parents=True)
    dest = tmp_path / "out"
    legacy = {
        "title": "BenchmarkReport.v0",
        "type": "object",
        "properties": {
            "metric_summaries": {
                "type": "array",
                "items": {"$ref": "MetricSummary.v0.schema.json"},
            }
        },
        "$defs": {},
    }
    (src / "BenchmarkReport.v0.schema.json").write_text(json.dumps(legacy), encoding="utf-8")
    result = sync_schemas_from_pcs_core(tmp_path / "pcs-core", dest_dir=dest)
    assert "BenchmarkReport.v0.inline_metric_summary" in result.copied
    patched = json.loads((dest / "BenchmarkReport.v0.json").read_text(encoding="utf-8"))
    assert not uses_legacy_metric_summary_ref(patched)
    assert "metric_summary" in patched["$defs"]
