"""The report must be derived from persisted target effects, not expected labels."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pcs_bench.effect_study import run_study


def test_study_generates_nine_independent_target_observations(tmp_path: Path):
    result = run_study(tmp_path / "experimental-effects.sqlite3")
    assert result["status"] == "pass"
    assert result["case_count"] == 9
    assert all(case["matches_expected"] for case in result["cases"])
    assert result["target_side_state"]["number_of_commits"] == 4
    assert result["target_side_state"]["final_balances"] == {"account:a": 115}
    cases = {entry["case"]: entry for entry in result["cases"]}
    assert cases["EFFECT-05-commit-response-lost"]["gateway_or_target_outcome"] == "unknown"
    assert cases["EFFECT-08-unmediated-bypass"]["authorized_at_policy"] is False
    assert cases["EFFECT-08-unmediated-bypass"]["observed_new_commits"] == 1
    assert cases["EFFECT-06-idempotent-retry"]["observed_new_commits"] == 0


def test_cli_study_output_is_json_with_explicit_limit(tmp_path: Path):
    output = tmp_path / "effect-study.json"
    result = subprocess.run(
        [sys.executable, "-m", "pcs_bench.effect_study", "--out", str(output)],
        capture_output=True, text=True, timeout=25, check=True,
    )
    assert "9 source-grounded cases" in result.stdout
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["protocol"] == "agent-effect-boundary-study-v1"
    assert record["status"] == "pass"
    assert "does not demonstrate" in record["assurance_limit"]
    assert len(record["source_digests"]["effect_target.py"]) == 64
