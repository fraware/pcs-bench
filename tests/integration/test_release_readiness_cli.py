"""Integration tests for release-readiness and gate policy."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app

ROOT = Path(__file__).resolve().parents[2]


def test_gate_rejects_live_with_fixture_fallback() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "gate",
            "--suite",
            "labtrust-qc-release",
            "--live",
            "--run-producer-benchmarks",
            "--use-producer-fixtures",
            "--out",
            "reports/tmp-gate.json",
            "--out-packet",
            "packets/tmp-gate",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 1
    assert "fixture" in result.output.lower() or "Release-grade" in result.output


def test_release_readiness_offline_fixtures_only() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "release-readiness",
            "--skip-fixtures",
            "--labtrust",
            str(ROOT.parent / "no-labtrust"),
            "--certifyedge",
            str(ROOT.parent / "no-certifyedge"),
            "--provability-fabric",
            str(ROOT.parent / "no-pf"),
            "--scientific-memory",
            str(ROOT.parent / "no-sm"),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code in (0, 2)
