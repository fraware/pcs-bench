"""CLI integration tests for producer ingest commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "producer_ingest"
    / "certifyedge"
    / "pcs_bench_ingest.v0.json"
)


def test_validate_producer_fixtures_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["validate-producer-fixtures"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_validate_ingest_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["validate-ingest", "--input", str(FIXTURE)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output


def test_ingest_producer_output_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "normalized.json"
    result = runner.invoke(
        app,
        [
            "ingest-producer-output",
            "--producer",
            "certifyedge",
            "--input",
            str(FIXTURE),
            "--out",
            str(out),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "v0"
    assert data.get("coverage", {}).get("certificate_completeness")
