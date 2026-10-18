"""Real native ACS/Cedar + enforcing Agent Hooks + separate target journal.

The integration is required in its own CI job. It is skipped in the default
pcs-bench job only because ACS is an optional, native pre-release dependency.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path

import pytest

if os.environ.get("ACS_EFFECT_INTEGRATION") != "1":
    pytest.skip("ACS_EFFECT_INTEGRATION not enabled", allow_module_level=True)

from agent_control_spec import __version__ as ACS_VERSION  # noqa: E402
from pcs_bench.acs_effect_host import AcsEffectHost  # noqa: E402
from pcs_bench.effect_boundary import Action  # noqa: E402
from pcs_bench.effect_study import disposable_target  # noqa: E402
from pcs_bench.effect_boundary import read_target  # noqa: E402


MANIFEST = Path(__file__).resolve().parents[1] / "fixtures/acs_effect/manifest.yaml"


def test_native_acs_release_is_the_selected_published_version():
    assert ACS_VERSION == "0.4.0a4"
    assert MANIFEST.is_file()
    assert (MANIFEST.parent / "effect_guard.cedar").is_file()


def test_real_cedar_allows_and_denies_against_target_journal(tmp_path: Path):
    async def scenario(url: str) -> None:
        host = AcsEffectHost(MANIFEST, epoch=7)
        baseline = Action("acs-good", "agent-1", "tenant-a", "account:a", 5)
        authorization = await host.authorize(baseline)
        assert authorization.permitted, authorization.reason
        allowed = await host.dispatch(url, baseline, authorization)
        assert allowed.status == "committed"
        assert len(read_target(url, "journal")["effects"]) == 1

        invalid = (
            replace(baseline, operation_id="bad-actor", principal="intruder"),
            replace(baseline, operation_id="bad-tenant", tenant="tenant-b"),
            replace(baseline, operation_id="bad-resource", resource="account:b"),
            replace(baseline, operation_id="bad-value", delta=20),
            replace(baseline, operation_id="bad-negative", delta=-1),
        )
        for action in invalid:
            verdict = await host.authorize(action)
            assert not verdict.permitted, (action, verdict.reason)
            outcome = await host.dispatch(url, action, verdict)
            assert outcome.status == "blocked"
        assert len(read_target(url, "journal")["effects"]) == 1
        assert read_target(url, "state")["balances"] == {"account:a": 5}

    with disposable_target(tmp_path / "acs-real.sqlite3") as url:
        asyncio.run(scenario(url))


def test_acs_decision_bound_to_exact_action_and_epoch(tmp_path: Path):
    async def scenario(url: str) -> None:
        host = AcsEffectHost(MANIFEST, epoch=2)
        action = Action("acs-mut", "agent-1", "tenant-a", "account:a", 4)
        approved = await host.authorize(action)
        assert approved.permitted, approved.reason
        mutation = await host.dispatch(url, replace(action, delta=9), approved)
        assert (mutation.status, mutation.reason) == (
            "blocked", "action_mutated_after_acs"
        )
        host.change_policy_state(epoch=3, revoked=True)
        stale = await host.dispatch(url, action, approved)
        assert (stale.status, stale.reason) == ("blocked", "policy_epoch_changed")

        revoked = await host.authorize(replace(action, operation_id="acs-revoked"))
        assert not revoked.permitted, revoked.reason
        assert len(read_target(url, "journal")["effects"]) == 0

    with disposable_target(tmp_path / "acs-mut.sqlite3") as url:
        asyncio.run(scenario(url))


def test_acs_authorized_commit_with_lost_reply_is_unknown(tmp_path: Path):
    async def scenario(url: str) -> None:
        host = AcsEffectHost(MANIFEST, epoch=4)
        action = Action("acs-unknown", "agent-1", "tenant-a", "account:a", 3)
        granted = await host.authorize(action)
        assert granted.permitted, granted.reason
        first = await host.dispatch(url, action, granted, drop_reply_after_commit=True)
        assert first.status == "unknown"
        assert len(read_target(url, "journal")["effects"]) == 1
        second = await host.dispatch(url, action, granted)
        assert second.status == "deduplicated"
        assert len(read_target(url, "journal")["effects"]) == 1

    with disposable_target(tmp_path / "acs-unknown.sqlite3") as url:
        asyncio.run(scenario(url))
