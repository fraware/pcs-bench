"""Real Cedar authorization with target-side Ed25519 authenticated commits."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

if os.environ.get("ACS_EFFECT_INTEGRATION") != "1":
    pytest.skip("native ACS pinned integration required", allow_module_level=True)

from agent_control_spec import __version__ as ACS_VERSION

from pcs_bench.signed_acs_study import run_study, signed_target

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures/acs_effect/manifest.yaml"


def test_real_acs_and_signed_target_preserve_distinct_security_boundaries(tmp_path: Path):
    assert ACS_VERSION == "0.4.0a4"
    database = tmp_path / "signed-acs.sqlite3"
    with signed_target(database) as (url, key, audience):
        result = asyncio.run(run_study(MANIFEST, url, database, key, audience))
    assert result["status"] == "pass"
    assert result["case_count"] == 10
    assert all(case["pass"] for case in result["cases"])
    assert result["target"]["authenticated_effects"] == 4
    assert result["target"]["balances"] == {"account:a": 11}
    assert result["target"]["key_ids"] == ["acs-lab-key"]
    assert len(result["acs"]["cedar_manifest_sha256"]) == 64
    assert len(result["acs"]["cedar_policy_sha256"]) == 64
    cases = {case["case"]: case for case in result["cases"]}
    assert cases["ACSS-06-key-valid-policy-revoked"]["actual_outcome"] == "revoked"
    assert cases["ACSS-07-old-stage-after-regrant"]["actual_outcome"] == (
        "stage_policy_epoch_stale"
    )
    assert cases["ACSS-09-valid-key-bypasses-cooperative-acs"]["observed_new_commits"] == 1
    assert cases["ACSS-10-key-revocation-before-commit"]["observed_new_commits"] == 0
    assert "No PKI" in result["assurance_limit"]
