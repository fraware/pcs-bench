"""Packet reproduce-smoke verification tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pcs_bench.cli import app
from pcs_bench.packet import export_benchmark_packet, verify_benchmark_packet
from pcs_bench.reports import save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary

BENCH_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = BENCH_ROOT / "benchmarks"


def _report_with_scimem_explain() -> BenchmarkReport:
    return BenchmarkReport(
        benchmark_suite_id="all",
        runs=[
            BenchmarkRun(
                run_id="r-valid",
                case_id="labtrust-valid-release-v0",
                suite_id="labtrust_qc_release",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            ),
            BenchmarkRun(
                run_id="r-invalid",
                case_id="labtrust-trace-hash-tamper-v0",
                suite_id="labtrust_qc_release",
                expected_status="failed",
                expected_system_outcome="rejected",
                observed_status="failed",
                observed_system_outcome="rejected",
                expected_failure_code="trace_hash_mismatch",
                observed_failure_code="trace_hash_mismatch",
                passed=True,
            ),
            BenchmarkRun(
                run_id="r-render",
                case_id="render-all-sections-v0",
                suite_id="scientific_memory_rendering",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            ),
        ],
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=1.0, applicability="measured"),
        ],
        summary={
            "execution_mode": "simulate",
            "evidence_grade": "developer",
            "live_cases": 0,
            "simulated_cases": 3,
        },
        coverage={
            "explain_quality": {
                "schema_version": "v0",
                "report_id": "explain-render-all-sections-v0",
                "suite_id": "scientific_memory_rendering",
                "case_id": "render-all-sections-v0",
                "producer_id": "scientific-memory",
                "required_sections": ["provenance", "verification", "limitations"],
                "sections": {
                    "provenance": {"present": True, "score": 1.0},
                    "verification": {"present": True, "score": 1.0},
                    "limitations": {"present": True, "score": 1.0},
                },
                "sections_present_count": 3,
                "sections_required_count": 3,
                "quality_score": 1.0,
                "gaps": [],
                "source_repo": "https://github.com/fraware/pcs-bench",
                "source_commit": "bb5d083dff2bb1060e88a5e643b46c0894947e05",
                "signature_or_digest": "sha256:127063f201d0da5c80a8670668f9ccdd9d4ea5cead95d8a0fae6e716fecb5c57",
            }
        },
    )


def test_verify_packet_reproduce_smoke(tmp_path: Path) -> None:
    from pcs_bench.config import BenchConfig

    report_path = tmp_path / "report.json"
    packet_dir = tmp_path / "packet"
    cfg = BenchConfig(benchmarks_root=BENCHMARKS)
    save_report(_report_with_scimem_explain(), report_path)
    export_benchmark_packet(report_path, packet_dir, config=cfg)

    result = verify_benchmark_packet(packet_dir, cfg, reproduce_smoke=True)
    assert result.valid, result.errors
    assert (packet_dir / "explain_quality.json").exists()
    report_path = packet_dir / "packet_reproduction_report.v0.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["checks"]["labtrust_valid_replay"]["ok"] is True
    assert report["checks"]["labtrust_invalid_rejection"]["ok"] is True
    assert report["checks"]["explain_quality_schema"]["ok"] is True
    assert report["checks"]["scientific_memory_rendering"]["ok"] is True


def test_verify_packet_cli_reproduce_smoke(tmp_path: Path) -> None:
    from pcs_bench.config import BenchConfig

    report_path = tmp_path / "report.json"
    packet_dir = tmp_path / "packet"
    cfg = BenchConfig(benchmarks_root=BENCHMARKS)
    save_report(_report_with_scimem_explain(), report_path)
    export_benchmark_packet(report_path, packet_dir, config=cfg)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["verify-packet", "--packet", str(packet_dir), "--reproduce-smoke"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
