"""Bundle producer merge provenance and normalized reports for reviewer packets."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pcs_bench.producer_ingest import ProducerMergeEntry


def attach_producer_artifacts_for_packet(
    report_path: Path,
    packet_dir: Path,
    *,
    scratch_dir: Path | None = None,
) -> list[Path]:
    """Copy merge manifest and per-producer normalized reports into the packet directory."""
    written: list[Path] = []
    packet_dir.mkdir(parents=True, exist_ok=True)
    manifest_src = report_path.parent / "producer_merge_manifest.v0.json"
    if manifest_src.is_file():
        dest = packet_dir / "producer_merge_manifest.v0.json"
        shutil.copy2(manifest_src, dest)
        written.append(dest)

    if not manifest_src.is_file():
        return written

    manifest = json.loads(manifest_src.read_text(encoding="utf-8"))
    bundle_root = packet_dir / "producer_ingests"
    bundle_root.mkdir(parents=True, exist_ok=True)
    for entry in manifest.get("producer_reports") or []:
        if not isinstance(entry, dict):
            continue
        producer_id = str(entry.get("producer_id", ""))
        if not producer_id:
            continue
        for label, key in (("ingest", "ingest_path"), ("normalized", "normalized_path")):
            raw = entry.get(key)
            if not raw:
                continue
            src = Path(raw)
            if not src.is_file():
                continue
            suffix = src.suffix or ".json"
            dest = bundle_root / producer_id / f"{label}{suffix}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            written.append(dest)

    if scratch_dir and scratch_dir.is_dir():
        scratch_dest = packet_dir / "producer_scratch"
        if scratch_dest.exists():
            shutil.rmtree(scratch_dest)
        shutil.copytree(scratch_dir, scratch_dest)
        written.append(scratch_dest)

    return written


def write_producer_gate_result(
    report_path: Path,
    *,
    errors: list[str],
    merge_entries: list[ProducerMergeEntry],
    release_grade: bool,
    use_fixture_fallback: bool,
) -> Path:
    """Write structured producer gate summary beside the aggregate report."""
    result_path = report_path.parent / "producer_gate_result.v0.json"
    summary: dict[str, Any] = {}
    if report_path.is_file():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            summary = data.get("summary") or {}
        except json.JSONDecodeError:
            summary = {}

    payload: dict[str, Any] = {
        "schema_version": "v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregate_report": report_path.name,
        "release_grade": release_grade,
        "use_fixture_fallback": use_fixture_fallback,
        "evidence_grade": summary.get("evidence_grade"),
        "fixture_fallback_used": summary.get("fixture_fallback_used"),
        "passed": not errors,
        "errors": errors,
        "producers_ingested": len(merge_entries),
        "producers_expected": 4,
        "producer_reports": [
            {
                "producer_id": e.producer_id,
                "suite_id": e.suite_id,
                "ingest_digest": e.ingest_digest,
                "ingest_path": e.ingest_path,
                "normalized_path": e.normalized_path,
            }
            for e in merge_entries
        ],
    }
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_path
