"""Unit tests for artifact analysis."""

from pathlib import Path

from pcs_bench.artifacts import analyze_certificate, analyze_registry, discover_release_layout, enrich_analysis

BENCH_ROOT = Path(__file__).resolve().parents[2]
VALID_RELEASE = (
    BENCH_ROOT
    / "benchmarks"
    / "labtrust_qc_release"
    / "valid"
    / "labtrust-valid-release-v0"
    / "input_artifacts"
)


def test_discover_release_layout():
    analysis = discover_release_layout(VALID_RELEASE)
    assert analysis.manifest_path is not None
    assert analysis.registry_path is not None
    assert len(analysis.certificate_paths) >= 1


def test_analyze_registry():
    registry = VALID_RELEASE / "artifact_registry.v0.json"
    total, checked = analyze_registry(registry)
    assert total == 3
    assert checked == 3


def test_enrich_analysis_certificate_coverage():
    analysis = discover_release_layout(VALID_RELEASE)
    enriched = enrich_analysis(analysis)
    assert enriched.certificate_field_coverage >= 0.9
    assert enriched.registry_coverage_ratio == 1.0


def test_analyze_certificate_complete():
    cert = VALID_RELEASE / "trace_certificate.v0.json"
    score, missing = analyze_certificate(cert)
    assert score >= 0.9
    assert len(missing) == 0
