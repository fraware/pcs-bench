"""Real ACS issuer -> independently appraised target credential evidence."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

if os.environ.get("ACS_EFFECT_INTEGRATION") != "1":
    pytest.skip("native ACS must be installed for this isolated integration", allow_module_level=True)

from agent_control_spec import __version__ as ACS_VERSION

from pcs_bench.acs_effect_host import AcsEffectHost
from pcs_bench.dual_authority_acs_study import laboratory_target, run_study

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures/acs_effect/manifest.yaml"


def test_genuine_acs_permission_requires_independent_target_side_issuer(tmp_path: Path):
    assert ACS_VERSION == "0.4.0a4"
    policy = AcsEffectHost(MANIFEST, legacy_cedar_principal_bridge=True)
    database = tmp_path / "dual-acs.sqlite3"
    with laboratory_target(database, policy.cedar_sha256) as (url, actor, issuer, aud):
        report = asyncio.run(run_study(MANIFEST, url, database, actor, issuer, aud))
    assert report["status"] == "pass"
    assert report["case_count"] == 8
    assert all(item["pass"] for item in report["cases"])
    assert report["target"]["authenticated_commits"] == 3
    assert report["target"]["balances"] == {"account:a": 9}
    assert report["target"]["issuer_ids"] == ["acs-policy-issuer"]
    assert len(report["manifest_sha256"]) == 64
    assert len(report["policy_sha256"]) == 64
    indexed = {item["case"]: item for item in report["cases"]}
    assert indexed["DUAL-02-actor-only-bypass-blocked"]["observed_commits"] == 0
    assert indexed["DUAL-05-revocation-after-staging"]["observed_commits"] == 0
    assert indexed["DUAL-07-honest-issuer-assumption"]["observed_commits"] == 1
    assert indexed["DUAL-08-revoked-policy-signer"]["observed_commits"] == 0
    assert "neither that ACS was" in report["limit"]
