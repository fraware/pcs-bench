"""Packet export of per-producer coverage from merge manifest."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.packet import export_benchmark_packet, verify_benchmark_packet
from pcs_bench.producer_ingest import ProducerMergeEntry, write_producer_merge_manifest
from pcs_bench.reports import save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun, MetricSummary

BENCH_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = BENCH_ROOT / "benchmarks"
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "producer_ingest"
    / "provability_fabric"
    / "pcs_bench_ingest.v0.json"
)


def _report_with_pf_coverage(tmp_path: Path) -> Path:
    from pcs_bench.producer_ingest import ingest_producer_output

    normalized = tmp_path / "pf.normalized.json"
    ingest_producer_output(
        "provability-fabric",
        FIXTURE,
        normalized,
        pcs_core_path=Path(__file__).resolve().parents[2] / "src" / "pcs_bench",
    )
    report = BenchmarkReport(
        benchmark_suite_id="all",
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="labtrust-valid-release-v0",
                suite_id="labtrust_qc_release",
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
        summary={"execution_mode": "simulate", "evidence_grade": "developer"},
        coverage=json.loads(normalized.read_text(encoding="utf-8")).get("coverage", {}),
    )
    report_path = tmp_path / "aggregate.json"
    save_report(report, report_path)
    write_producer_merge_manifest(
        report_path,
        [
            ProducerMergeEntry(
                producer_id="provability-fabric",
                suite_id="pf-admission-v0",
                source_repo="https://example.com/pf",
                source_commit="a" * 40,
                ingest_digest="sha256:" + "b" * 64,
                ingest_path=str(FIXTURE),
                normalized_path=str(normalized),
            )
        ],
    )
    return report_path


def test_packet_exports_producer_coverage(tmp_path: Path) -> None:
    report_path = _report_with_pf_coverage(tmp_path)
    packet_dir = tmp_path / "packet"
    cfg = BenchConfig(benchmarks_root=BENCHMARKS)
    export_benchmark_packet(report_path, packet_dir, config=cfg)
    pf_explain = packet_dir / "producer_coverage" / "provability-fabric" / "explain_quality.json"
    assert pf_explain.is_file()
    doc = json.loads(pf_explain.read_text(encoding="utf-8"))
    assert doc.get("producer_id") == "provability-fabric"
