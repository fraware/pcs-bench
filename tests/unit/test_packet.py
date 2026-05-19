"""Unit tests for benchmark packet export."""

from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app

BENCH_ROOT = Path(__file__).resolve().parents[2]


def test_packet_export(tmp_path):
    runner = CliRunner()
    report = tmp_path / "report.json"
    packet_dir = tmp_path / "packet"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.chdir(BENCH_ROOT)
        runner.invoke(
            app,
            ["run", "--suite", "labtrust-qc-release", "--simulate", "--out", str(report)],
            catch_exceptions=False,
        )
    result = runner.invoke(
        app,
        ["packet", "--report", str(report), "--out", str(packet_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert (packet_dir / "BenchmarkReport.v0.json").exists()
    assert (packet_dir / "README.md").exists()
    assert (packet_dir / "report.md").exists()
