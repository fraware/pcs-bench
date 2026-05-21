"""Tests for fixture manifest."""

from pcs_bench.config import BenchConfig
from pcs_bench.reproducibility import build_fixture_manifest, save_fixture_manifest, verify_fixture_manifest


def test_fixture_manifest_roundtrip(tmp_path):
    cfg = BenchConfig(benchmarks_root=tmp_path / "benchmarks")
    suite = tmp_path / "benchmarks" / "demo"
    case = suite / "valid" / "c1"
    case.mkdir(parents=True)
    (case / "benchmark_case.v0.json").write_text('{"schema_version":"v0","case_id":"c1","task_id":"t","workflow_id":"w","case_kind":"k","expected_status":"Admitted"}', encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    m = build_fixture_manifest(cfg)
    save_fixture_manifest(m, manifest_path)
    assert verify_fixture_manifest(cfg, manifest_path).valid


def test_fixture_manifest_excludes_itself(tmp_path):
    cfg = BenchConfig(benchmarks_root=tmp_path / "benchmarks")
    suite = tmp_path / "benchmarks" / "demo"
    case = suite / "valid" / "c1"
    case.mkdir(parents=True)
    (case / "benchmark_case.v0.json").write_text(
        '{"schema_version":"v0","case_id":"c1","task_id":"t","workflow_id":"w",'
        '"case_kind":"valid_release","expected_status":"passed"}',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "benchmarks" / "fixture_manifest.json"
    m = build_fixture_manifest(cfg)
    save_fixture_manifest(m, manifest_path)
    paths = {e.path.replace("\\", "/") for e in m.entries}
    assert "fixture_manifest.json" not in paths
    assert verify_fixture_manifest(cfg, manifest_path).valid
