"""Unit tests for configuration."""

from pathlib import Path

from pcs_bench.config import BenchConfig, SUITE_ALIASES


def test_suite_aliases_resolve():
    assert SUITE_ALIASES["labtrust-qc-release"] == "labtrust_qc_release"
    assert SUITE_ALIASES["all"] == "all"


def test_resolve_suites_all():
    cfg = BenchConfig()
    suites = cfg.resolve_suites("all")
    assert "labtrust_qc_release" in suites
    assert len(suites) >= 6


def test_load_default_config():
    cfg = BenchConfig.load(Path("pcs-bench-nonexistent.yaml"))
    assert cfg.thresholds.failure_localization_accuracy == 0.90


def test_apply_cli_overrides(tmp_path):
    cfg = BenchConfig()
    pcs = tmp_path / "pcs-core"
    pcs.mkdir()
    updated = cfg.apply_cli_overrides(pcs_core=pcs)
    assert updated.repos.pcs_core == pcs.resolve()
