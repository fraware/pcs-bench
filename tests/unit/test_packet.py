"""Unit tests for benchmark packet export."""


from typer.testing import CliRunner

from pcs_bench.cli import app
from pcs_bench.reports import save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary


def test_packet_export(tmp_path):
    report_path = tmp_path / "report.json"
    packet_dir = tmp_path / "packet"

    bench_report = BenchmarkReport(
        benchmark_suite_id="labtrust-qc-release-v0",
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="labtrust-valid-release-v0",
                suite_id="labtrust-qc-release-v0",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
            ),
            BenchmarkRun(
                run_id="r2",
                case_id="labtrust-trace-hash-tamper-v0",
                suite_id="labtrust-qc-release-v0",
                expected_status="failed",
                expected_system_outcome="rejected",
                observed_status="failed",
                observed_system_outcome="rejected",
                expected_failure_code="trace_hash_mismatch",
                observed_failure_code="trace_hash_mismatch",
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
            "simulated_cases": 2,
        },
    )
    save_report(bench_report, report_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["packet", "--report", str(report_path), "--out", str(packet_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert (packet_dir / "BenchmarkReport.v0.json").exists()
    assert (packet_dir / "README.md").exists()
    assert (packet_dir / "report.html").exists()
    assert (packet_dir / "report.md").exists()
    assert (packet_dir / "limitations.md").exists()
    assert (packet_dir / "environment_summary.json").exists()
    assert (packet_dir / "reproduce.sh").exists()

    verify = runner.invoke(
        app,
        ["verify-packet", "--packet", str(packet_dir)],
        catch_exceptions=False,
    )
    assert verify.exit_code == 0, verify.output
