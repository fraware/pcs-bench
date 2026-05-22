"""LabTrust extended artifact_refs in PcsBenchIngest.v0."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.ingest_validation import (
    _is_labtrust_extended_artifact_ref,
    _pcs_core_ingest_body,
    validate_ingest_semantics,
)


_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"
REPRO_FIXTURE = _FIXTURE_ROOT / "labtrust_reproducibility" / "pcs_bench_ingest.v0.json"
CASE_SUITE_FIXTURE = _FIXTURE_ROOT / "labtrust" / "pcs_bench_ingest.v0.json"
FIXTURE = REPRO_FIXTURE if REPRO_FIXTURE.is_file() else CASE_SUITE_FIXTURE


def test_labtrust_extended_ref_detection() -> None:
    ref = {
        "artifact_type": "LabtrustBenchmarkRunSummary.v0",
        "path": "benchmark_run.v0.json",
        "role": "reproducibility_evidence",
    }
    assert _is_labtrust_extended_artifact_ref(ref)


def test_pcs_core_body_strips_extended_refs() -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    body = _pcs_core_ingest_body(doc)
    refs = body.get("artifact_refs") or []
    assert refs
    assert all(not _is_labtrust_extended_artifact_ref(r) for r in refs)


def test_semantics_allow_labtrust_extended_types() -> None:
    doc = {
        "schema_version": "v0",
        "producer_id": "labtrust-gym",
        "suite_id": "x",
        "workflow_id": "hospital_lab.qc_release",
        "benchmark_runs": [{"signature_or_digest": "sha256:" + "a" * 64}],
        "coverage_reports": [],
        "failure_localization_reports": [],
        "explain_quality_reports": [],
        "profile_coverage_reports": [],
        "commands": [],
        "logs": [],
        "source_repo": "https://example.com",
        "source_commit": "5eac714fd7dc813d2523febcb85c56821558a1b7",
        "signature_or_digest": "sha256:" + "b" * 64,
        "artifact_refs": [
            {
                "artifact_type": "LabtrustBenchmarkRunSummary.v0",
                "path": "benchmark_run.v0.json",
                "sha256": "sha256:" + "c" * 64,
                "role": "reproducibility_evidence",
            }
        ],
    }
    errors = validate_ingest_semantics(doc)
    assert not any("unsupported artifact_type" in e for e in errors)
