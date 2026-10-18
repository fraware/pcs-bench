"""Pinned native ACS plus target-owned commit-time authorization evidence."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

if os.environ.get("ACS_EFFECT_INTEGRATION") != "1":
    pytest.skip("native ACS is an optional, pinned CI dependency", allow_module_level=True)

from agent_control_spec import __version__ as ACS_VERSION

from pcs_bench.guarded_study import guarded_server, run_study

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures/acs_effect/manifest.yaml"


def test_target_side_revocation_blocks_previously_permitted_acs_action(tmp_path: Path):
    assert ACS_VERSION == "0.4.0a4"
    database = tmp_path / "test.sqlite3"
    with guarded_server(database) as url:
        report = asyncio.run(run_study(MANIFEST, url, database))
    assert report["status"] == "pass"
    assert report["case_count"] == 9
    assert report["acs"]["policy_backend"] == "Cedar"
    assert report["acs"]["legacy_principal_bridge"] is True
    assert len(report["acs"]["manifest_sha256"]) == 64
    assert len(report["acs"]["cedar_sha256"]) == 64
    by_id = {case["case"]: case for case in report["cases"]}
    assert all(c["pass"] for c in report["cases"])
    assert by_id["ACST-04-revocation-before-commit"]["actual_http"] == 403
    assert by_id["ACST-04-revocation-before-commit"]["observed_new_effects"] == 0
    assert by_id["ACST-05-old-stage-after-regrant"]["actual_http"] == 409
    assert by_id["ACST-07-historical-idempotent-replay"]["observed_new_effects"] == 0
    assert by_id["ACST-08-unmediated-revoked-request"]["actual_http"] == 403
    assert by_id["ACST-09-self-asserted-identity-gap"]["observed_new_effects"] == 1
    assert report["target"]["effects"] == 3
    assert report["target"]["balances"] == {"account:a": 11}
    assert sorted(report["target"]["effect_epochs"]) == [1, 3, 5]
    assert "caller-asserted" in report["assurance_limit"]
