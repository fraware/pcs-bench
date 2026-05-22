"""Integration test for offline producer gate aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app

ROOT = Path(__file__).resolve().parents[2]


def test_gate_producer_offline_aggregation(tmp_path: Path) -> None:
    cfg_path = tmp_path / "pcs-bench-isolated.yaml"
    cfg_path.write_text(
        f"""repos:
  pcs_core: {tmp_path / "no-pcs-core"}
  labtrust: {tmp_path / "no-labtrust"}
  certifyedge: {tmp_path / "no-certifyedge"}
  provability_fabric: {tmp_path / "no-pf"}
  scientific_memory: {tmp_path / "no-sm"}
""",
        encoding="utf-8",
    )
    runner = CliRunner()
    out = tmp_path / "reports" / "producer-gate.json"
    packet = tmp_path / "packets" / "producer-gate"
    result = runner.invoke(
        app,
        [
            "gate",
            "--config",
            str(cfg_path),
            "--suite",
            "all",
            "--run-producer-benchmarks",
            "--use-producer-fixtures",
            "--reproduce-smoke",
            "--out",
            str(out),
            "--out-packet",
            str(packet),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert (out.parent / "producer_merge_manifest.v0.json").is_file()
    assert (out.parent / "producer_gate_result.v0.json").is_file()
    gate_result = json.loads((out.parent / "producer_gate_result.v0.json").read_text())
    assert gate_result["passed"] is True
    assert gate_result["producers_ingested"] == 4
    assert (packet / "packet_reproduction_report.v0.json").is_file()
    assert (packet / "producer_merge_manifest.v0.json").is_file()
    smoke = json.loads((packet / "packet_reproduction_report.v0.json").read_text(encoding="utf-8"))
    assert smoke.get("passed") is True

    from pcs_bench.config import BenchConfig
    from pcs_bench.validation import validate_report_json

    cfg = BenchConfig.load(cfg_path)
    schema_root = ROOT / "src" / "pcs_bench"
    report_errors = validate_report_json(out, cfg, schema_source=schema_root)
    assert report_errors == [], report_errors

    report_doc = json.loads(out.read_text(encoding="utf-8"))
    summary = report_doc.get("summary") or {}
    assert summary.get("evidence_grade") == "developer"
    assert "fixture_fallback_used" not in summary
    assert gate_result.get("use_fixture_fallback") is True
