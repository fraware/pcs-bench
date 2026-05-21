"""Tests for producer output normalization."""

import json
from pathlib import Path

from pcs_bench.producer_ingest import ingest_producer_output


def test_ingest_minimal_producer_report(tmp_path: Path) -> None:
    producer_dir = tmp_path / "runs"
    producer_dir.mkdir()
    (producer_dir / "BenchmarkReport.v0.json").write_text(
        json.dumps(
            {
                "schema_version": "v0",
                "benchmark_suite_id": "tool-use-safety-v0",
                "runs": [
                    {
                        "run_id": "r1",
                        "case_id": "tool-use-valid-v0",
                        "expected_status": "passed",
                        "observed_status": "passed",
                        "passed": True,
                    }
                ],
                "metrics": ["release_reproducibility_score"],
                "metric_summaries": [
                    {
                        "name": "release_reproducibility_score",
                        "score": 1.0,
                        "applicability": "measured",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "normalized.json"
    ingest_producer_output("certifyedge", producer_dir, out, suite_id="tool-use-safety-v0")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "v0"
    assert data["metrics"] == ["release_reproducibility_score"]
    assert data["runs"][0]["case_id"] == "tool-use-valid-v0"
