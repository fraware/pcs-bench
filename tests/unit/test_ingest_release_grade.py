"""Release-grade ingest adequacy checks."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from pcs_bench.ingest_validation import (
    load_ingest_document,
    validate_ingest_release_adequacy,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"


@pytest.mark.parametrize(
    "fixture_dir",
    ["certifyedge", "provability_fabric", "scientific_memory", "labtrust"],
)
def test_all_fixtures_pass_release_grade(fixture_dir: str) -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / fixture_dir / "pcs_bench_ingest.v0.json")
    errors = validate_ingest_release_adequacy(doc)
    assert errors == [], errors


def test_release_grade_rejects_empty_runs() -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / "labtrust/pcs_bench_ingest.v0.json")
    bad = deepcopy(doc)
    bad["benchmark_runs"] = []
    errors = validate_ingest_release_adequacy(bad)
    assert any("benchmark_runs" in e for e in errors)


def test_release_grade_certifyedge_coverage_only_exception() -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / "certifyedge/pcs_bench_ingest.v0.json")
    doc = deepcopy(doc)
    doc["benchmark_runs"] = []
    errors = validate_ingest_release_adequacy(doc)
    assert not any("benchmark_runs" in e for e in errors)


def test_release_grade_rejects_pf_missing_failure_localization() -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / "provability_fabric/pcs_bench_ingest.v0.json")
    bad = deepcopy(doc)
    bad["failure_localization_reports"] = []
    errors = validate_ingest_release_adequacy(bad)
    assert any("failure_localization_reports" in e for e in errors)


def test_release_grade_rejects_certifyedge_missing_profile_coverage() -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / "certifyedge/pcs_bench_ingest.v0.json")
    bad = deepcopy(doc)
    bad["profile_coverage_reports"] = []
    bad["benchmark_runs"] = []
    errors = validate_ingest_release_adequacy(bad)
    assert any("profile_coverage_reports" in e for e in errors)


def test_release_grade_skips_sidecar_check_on_fixture_roots() -> None:
    doc, base = load_ingest_document(FIXTURE_ROOT / "certifyedge/pcs_bench_ingest.v0.json")
    errors = validate_ingest_release_adequacy(doc, search_roots=(base.resolve(),))
    assert not any("sidecar file missing" in e for e in errors)


def test_release_grade_rejects_all_zero_commit() -> None:
    doc, _ = load_ingest_document(FIXTURE_ROOT / "labtrust/pcs_bench_ingest.v0.json")
    bad = deepcopy(doc)
    bad["source_commit"] = "0" * 40
    errors = validate_ingest_release_adequacy(bad)
    assert any("all zeros" in e for e in errors)
