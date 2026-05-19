"""Integration tests for benchmark CLI."""

from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app

BENCH_ROOT = Path(__file__).resolve().parents[2]


def test_simulate_labtrust_suite(tmp_path):
    runner = CliRunner()
    out = tmp_path / "report.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.chdir(BENCH_ROOT)
        result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "labtrust-qc-release",
                "--simulate",
                "--out",
                str(out),
                "--workspace",
                str(tmp_path / "ws"),
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output
    assert out.exists()
    data = out.read_text(encoding="utf-8")
    assert '"schema_version": "v0"' in data
    assert "release_reproducibility_score" in data


def test_simulate_all_suites_ci(tmp_path):
    runner = CliRunner()
    out = tmp_path / "ci.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.chdir(BENCH_ROOT)
        result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "all",
                "--simulate",
                "--ci",
                "--out",
                str(out),
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output


def test_validate_cases():
    runner = CliRunner()
    with runner.isolated_filesystem():
        import os

        os.chdir(BENCH_ROOT)
        result = runner.invoke(
            app,
            ["validate-cases", "--suite", "all", "--dry-run"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output


def test_list_suites():
    runner = CliRunner()
    result = runner.invoke(app, ["list-suites"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "labtrust-qc-release" in result.output


def test_report_markdown(tmp_path):
    runner = CliRunner()
    report_json = tmp_path / "report.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.chdir(BENCH_ROOT)
        runner.invoke(
            app,
            [
                "run",
                "--suite",
                "labtrust-qc-release",
                "--simulate",
                "--out",
                str(report_json),
            ],
            catch_exceptions=False,
        )
    md_out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["report", "--input", str(report_json), "--format", "markdown", "--out", str(md_out)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "# PCS Benchmark Report" in md_out.read_text(encoding="utf-8")
