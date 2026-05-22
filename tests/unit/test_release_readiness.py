"""Unit tests for release readiness evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.release_readiness import evaluate_release_readiness
from pcs_bench.report_export import enrich_report_for_export
from pcs_bench.reports import report_digest, save_report
from pcs_bench.schemas import BenchmarkReport, BenchmarkRun


def test_evaluate_release_readiness_live_ci_artifacts(tmp_path: Path) -> None:
    report = BenchmarkReport(
        benchmark_suite_id="all",
        runs=[
            BenchmarkRun(
                run_id="r1",
                case_id="c1",
                suite_id="s",
                expected_status="passed",
                expected_system_outcome="admitted",
                observed_status="passed",
                observed_system_outcome="admitted",
                passed=True,
                execution_kind="live",
            )
        ],
        summary={
            "execution_mode": "live",
            "evidence_grade": "release",
            "live_cases": 1,
            "fixture_fallback_used": False,
        },
    )
    enrich_report_for_export(report)
    report.finalize(digest=report_digest(report))
    report_path = tmp_path / "live-ci.json"
    save_report(report, report_path)

    manifest = {
        "schema_version": "v0",
        "producer_reports": [{"producer_id": f"p{i}"} for i in range(4)],
    }
    (tmp_path / "producer_merge_manifest.v0.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    cfg = BenchConfig()
    schema_root = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"
    readiness = evaluate_release_readiness(
        cfg,
        schema_root=schema_root,
        release_grade=False,
        verify_live_ci=report_path,
        verify_live_packet=None,
        include_fixture_validation=False,
    )
    names = {c["name"] for c in readiness.checks}
    assert "live_ci_report" in names
    assert "live_ci_evidence_grade" in names
    assert "producer_merge_manifest" in names
    assert any(c["name"] == "live_ci_evidence_grade" and c["ok"] for c in readiness.checks)
