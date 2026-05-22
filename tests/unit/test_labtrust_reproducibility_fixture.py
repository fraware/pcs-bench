"""LabTrust reproducibility producer fixture (extended artifact_refs + sidecars)."""

from __future__ import annotations

import json
from pathlib import Path

from pcs_bench.ingest_validation import validate_ingest_json

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "producer_ingest"
    / "labtrust_reproducibility"
)
INGEST = FIXTURE_ROOT / "pcs_bench_ingest.v0.json"


def test_reproducibility_fixture_present() -> None:
    assert INGEST.is_file(), f"missing {INGEST}"


def test_reproducibility_fixture_has_portable_commands() -> None:
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    commands = doc.get("commands") or []
    assert commands
    cmd = str(commands[0].get("command", ""))
    assert "C:" not in cmd and "\\\\" not in cmd
    assert "labtrust benchmark-reproducibility" in cmd


def test_reproducibility_fixture_validates_developer_grade() -> None:
    errors = validate_ingest_json(INGEST, Path(__file__).resolve().parents[2] / "src")
    assert not errors, errors
