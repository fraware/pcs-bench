"""Tests for producer artifact bundling and gate result sidecars."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.producer_artifacts import (
    attach_producer_artifacts_for_packet,
    write_producer_gate_result,
)
from pcs_bench.producer_ingest import ProducerMergeEntry


def test_write_producer_gate_result(tmp_path: Path) -> None:
    report = tmp_path / "aggregate.json"
    report.write_text("{}", encoding="utf-8")
    entries = [
        ProducerMergeEntry(
            producer_id="certifyedge",
            suite_id="s",
            source_repo="https://example.com",
            source_commit="a" * 40,
            ingest_digest="sha256:" + "b" * 64,
            ingest_path="/ingest.json",
            normalized_path="/norm.json",
        )
    ]
    path = write_producer_gate_result(
        report,
        errors=[],
        merge_entries=entries,
        release_grade=True,
        use_fixture_fallback=False,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["producers_ingested"] == 1


def test_attach_producer_artifacts_for_packet(tmp_path: Path) -> None:
    report = tmp_path / "aggregate.json"
    report.write_text("{}", encoding="utf-8")
    ingest = tmp_path / "ingest.json"
    ingest.write_text('{"producer_id":"pf"}', encoding="utf-8")
    normalized = tmp_path / "pf.normalized.json"
    normalized.write_text('{"coverage":{}}', encoding="utf-8")
    manifest = tmp_path / "producer_merge_manifest.v0.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "v0",
                "producer_reports": [
                    {
                        "producer_id": "provability-fabric",
                        "ingest_path": str(ingest),
                        "normalized_path": str(normalized),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    packet = tmp_path / "packet"
    written = attach_producer_artifacts_for_packet(report, packet)
    assert (packet / "producer_merge_manifest.v0.json").is_file()
    assert any("producer_ingests" in str(p) for p in written)
