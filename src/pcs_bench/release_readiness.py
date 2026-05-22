"""Aggregate PCS release readiness checks for pcs-bench and producer repos."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pcs_bench.config import BenchConfig
from pcs_bench.packet import verify_benchmark_packet
from pcs_bench.producer_doctor import run_producer_doctor
from pcs_bench.producer_fixtures import validate_all_producer_fixtures
from pcs_bench.producer_gate import PRODUCER_BENCHMARKS, _repo_for_producer
from pcs_bench.ingest_validation import validate_ingest_json


@dataclass
class ReleaseReadinessResult:
    ready: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "v0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ready": self.ready,
            "checks": self.checks,
            "errors": self.errors,
        }


def _append_check(
    result: ReleaseReadinessResult,
    *,
    name: str,
    ok: bool,
    detail: str,
) -> None:
    result.checks.append({"name": name, "ok": ok, "detail": detail})
    if not ok:
        result.errors.append(f"{name}: {detail}")


def evaluate_release_readiness(
    cfg: BenchConfig,
    *,
    schema_root: Path,
    release_grade: bool = True,
    verify_live_ci: Path | None = None,
    verify_live_packet: Path | None = None,
    include_fixture_validation: bool = True,
) -> ReleaseReadinessResult:
    """Run doctor, producer ingest checks, fixtures, and optional live-ci artifact verification."""
    result = ReleaseReadinessResult(ready=True)

    doctor = run_producer_doctor(cfg, schema_root=schema_root, release_grade=release_grade)
    _append_check(
        result,
        name="producer_doctor",
        ok=doctor.to_dict().get("all_ready", False),
        detail=f"{sum(1 for p in doctor.producers if p.ready)}/{len(doctor.producers)} producers ready",
    )

    ingest_failures = 0
    for spec in PRODUCER_BENCHMARKS:
        repo = _repo_for_producer(cfg, spec.producer)
        path = repo / spec.ingest_rel_path
        if not path.is_file():
            ingest_failures += 1
            continue
        errors = validate_ingest_json(
            path,
            schema_root,
            release_grade=release_grade,
            producer_repo=repo if repo.is_dir() else None,
        )
        if errors:
            ingest_failures += 1
    _append_check(
        result,
        name="producer_ingests",
        ok=ingest_failures == 0,
        detail=f"{len(PRODUCER_BENCHMARKS) - ingest_failures}/{len(PRODUCER_BENCHMARKS)} valid"
        + (" (release-grade)" if release_grade else ""),
    )

    if include_fixture_validation:
        fixture_failures = [
            r for r in validate_all_producer_fixtures(schema_root, release_grade=release_grade)
            if not r.valid
        ]
        _append_check(
            result,
            name="producer_fixtures",
            ok=not fixture_failures,
            detail=f"{len(fixture_failures)} fixture failure(s)",
        )

    if verify_live_ci and verify_live_ci.is_file():
        from pcs_bench.validation import validate_report_json

        report_errors = validate_report_json(verify_live_ci, cfg)
        _append_check(
            result,
            name="live_ci_report",
            ok=not report_errors,
            detail=str(verify_live_ci),
        )
        summary = json.loads(verify_live_ci.read_text(encoding="utf-8")).get("summary") or {}
        grade = summary.get("evidence_grade")
        gate_result_path = verify_live_ci.parent / "producer_gate_result.v0.json"
        fallback = summary.get("fixture_fallback_used")
        if gate_result_path.is_file():
            try:
                gate_result = json.loads(gate_result_path.read_text(encoding="utf-8"))
                fallback = gate_result.get("use_fixture_fallback", fallback)
            except json.JSONDecodeError:
                pass
        _append_check(
            result,
            name="live_ci_evidence_grade",
            ok=grade == "release" and not fallback,
            detail=f"evidence_grade={grade!r} fixture_fallback={fallback!r}",
        )
    elif verify_live_ci:
        _append_check(
            result,
            name="live_ci_report",
            ok=False,
            detail=f"missing {verify_live_ci}",
        )

    if verify_live_packet and verify_live_packet.is_dir():
        packet_result = verify_benchmark_packet(
            verify_live_packet, cfg, reproduce_smoke=True
        )
        _append_check(
            result,
            name="live_ci_packet",
            ok=packet_result.valid,
            detail=str(verify_live_packet),
        )
        smoke_path = verify_live_packet / "packet_reproduction_report.v0.json"
        _append_check(
            result,
            name="packet_reproduction_report",
            ok=smoke_path.is_file(),
            detail=str(smoke_path) if smoke_path.is_file() else "missing packet_reproduction_report.v0.json",
        )
    elif verify_live_packet:
        _append_check(
            result,
            name="live_ci_packet",
            ok=False,
            detail=f"missing {verify_live_packet}",
        )

    manifest = (
        verify_live_ci.parent / "producer_merge_manifest.v0.json"
        if verify_live_ci
        else None
    )
    if manifest and manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        count = len(data.get("producer_reports") or [])
        _append_check(
            result,
            name="producer_merge_manifest",
            ok=count >= len(PRODUCER_BENCHMARKS),
            detail=f"{count} producer entries",
        )

    result.ready = not result.errors
    return result
