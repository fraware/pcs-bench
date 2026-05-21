"""Tests for PcsBenchIngest.v0 validation and producer output normalization."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pcs_bench.ingest_validation import (
    load_ingest_document,
    validate_ingest_data_strict,
    validate_ingest_json,
)
from pcs_bench.producer_ingest import ingest_producer_output

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"
_PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"


def _pcs_core() -> Path:
    candidate = Path(__file__).resolve().parents[3] / "pcs-core"
    if (candidate / "schemas").is_dir():
        return candidate
    return _PKG_ROOT


def _fixture_path(name: str) -> Path:
    return FIXTURE_ROOT / name / "pcs_bench_ingest.v0.json"


@pytest.mark.parametrize(
    ("producer", "fixture_dir"),
    [
        ("certifyedge", "certifyedge"),
        ("provability-fabric", "provability_fabric"),
        ("scientific-memory", "scientific_memory"),
        ("labtrust-gym", "labtrust"),
    ],
)
def test_validate_producer_ingest(producer: str, fixture_dir: str) -> None:
    errors = validate_ingest_json(_fixture_path(fixture_dir), _pcs_core())
    assert errors == [], errors


def test_ingest_to_benchmark_report(tmp_path: Path) -> None:
    out = tmp_path / "normalized.json"
    ingest_producer_output(
        "certifyedge",
        _fixture_path("certifyedge"),
        out,
        pcs_core_path=_pcs_core(),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "v0"
    assert data["producer_id"] == "pcs-bench"
    assert "certificate_completeness_score" in data["metrics"]
    assert data["runs"] or data["coverage"].get("certificate_completeness")
    if data["runs"]:
        assert "case_id" in data["runs"][0]
    coverage = data.get("coverage", {})
    if coverage.get("certificate_completeness"):
        assert coverage["certificate_completeness"]["coverage_id"]
    if coverage.get("explain_quality"):
        assert coverage["explain_quality"]["case_id"]


def test_ingest_rejects_path_reference_when_object_required(tmp_path: Path) -> None:
    doc, _ = load_ingest_document(_fixture_path("certifyedge"))
    bad = deepcopy(doc)
    bad["artifact_refs"] = ["../native/private.json"]
    errors = validate_ingest_data_strict(bad, _pcs_core())
    assert any("artifact_refs[0]" in err and "path string" in err for err in errors)


def test_ingest_rejects_placeholder_commit(tmp_path: Path) -> None:
    doc, _ = load_ingest_document(_fixture_path("labtrust"))
    bad = deepcopy(doc)
    bad["source_commit"] = "placeholder"
    errors = validate_ingest_data_strict(bad, _pcs_core())
    assert any("source_commit" in err for err in errors)


def test_validate_pf_ingest() -> None:
    test_validate_producer_ingest("provability-fabric", "provability_fabric")


def test_validate_scientific_memory_ingest() -> None:
    test_validate_producer_ingest("scientific-memory", "scientific_memory")


def test_validate_labtrust_ingest() -> None:
    test_validate_producer_ingest("labtrust-gym", "labtrust")


def test_validate_certifyedge_ingest() -> None:
    test_validate_producer_ingest("certifyedge", "certifyedge")
