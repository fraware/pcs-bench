"""Tests for producer-doctor diagnostics."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.producer_doctor import run_producer_doctor
from pcs_bench.producer_gate import PRODUCER_BENCHMARKS

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "producer_ingest"
_PKG_ROOT = Path(__file__).resolve().parents[2] / "src" / "pcs_bench"

_REPO_FIXTURE_DIR = {
    "certifyedge": "certifyedge",
    "provability-fabric": "provability_fabric",
    "scientific-memory": "scientific_memory",
    "labtrust-gym": "labtrust",
}


def _pcs_core() -> Path:
    candidate = Path(__file__).resolve().parents[3] / "pcs-core"
    if (candidate / "schemas").is_dir():
        return candidate
    return _PKG_ROOT


def test_producer_doctor_json_report(tmp_path: Path) -> None:
    cfg = BenchConfig()
    cfg.repos.pcs_core = _pcs_core()
    for spec in PRODUCER_BENCHMARKS:
        fixture_dir = _REPO_FIXTURE_DIR[spec.producer]
        repo = tmp_path / spec.producer
        src = FIXTURE_ROOT / fixture_dir / "pcs_bench_ingest.v0.json"
        dest = repo / spec.ingest_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if spec.producer == "certifyedge":
            cfg.repos.certifyedge = repo
        elif spec.producer == "provability-fabric":
            cfg.repos.provability_fabric = repo
        elif spec.producer == "scientific-memory":
            cfg.repos.scientific_memory = repo
        elif spec.producer == "labtrust-gym":
            cfg.repos.labtrust = repo

    result = run_producer_doctor(cfg, schema_root=_pcs_core(), release_grade=False)
    payload = result.to_dict()
    assert payload["schema_version"] == "v0"
    assert len(payload["producers"]) == 4
    json.dumps(payload)
