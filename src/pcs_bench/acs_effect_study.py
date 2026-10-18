"""Machine-readable experiment using real ACS Cedar and a separate target ledger.

This produces controlled-experiment observations only; its "pass" status
means expected test-case outcomes were reproduced, not that an external
deployment is certified safe.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pcs_bench.acs_effect_host import AcsEffectHost
from pcs_bench.effect_boundary import Action, post_commit, read_target
from pcs_bench.effect_study import disposable_target


async def run_acs_study(manifest: Path, url: str) -> dict[str, Any]:
    from agent_control_spec import __version__ as acs_version

    host = AcsEffectHost(manifest, epoch=4, legacy_cedar_principal_bridge=True)
    cases: list[dict[str, Any]] = []

    def count() -> int:
        return len(read_target(url, "journal")["effects"])

    def record(name: str, before: int, expected_new: int, actual_outcome: str, expected: str) -> None:
        observed_new = count() - before
        cases.append({
            "case": name,
            "expected_outcome": expected,
            "actual_outcome": actual_outcome,
            "expected_new_commits": expected_new,
            "observed_new_commits": observed_new,
            "pass": actual_outcome == expected and observed_new == expected_new,
        })

    original = Action("acs-allowed", "agent-1", "tenant-a", "account:a", 5)
    before = count()
    allowed = await host.authorize(original)
    committed = await host.dispatch(url, original, allowed)
    record("ACS-01-allowed-effect", before, 1, committed.status, "committed")

    before = count()
    forbidden = replace(original, operation_id="acs-denied", delta=25)
    denial = await host.authorize(forbidden)
    blocked = await host.dispatch(url, forbidden, denial)
    record("ACS-02-cedar-denied", before, 0,
           f"{blocked.status}:{denial.reason}", "blocked:effect_delta_excessive")

    before = count()
    mutated = replace(original, operation_id="acs-mutated")
    auth = await host.authorize(mutated)
    mutation = await host.dispatch(url, replace(mutated, delta=8), auth)
    record("ACS-03-binding", before, 0, mutation.reason, "action_mutated_after_acs")

    before = count()
    host.change_policy_state(epoch=5, revoked=True)
    revocation = await host.authorize(replace(original, operation_id="acs-revoked"))
    record("ACS-04-policy-revocation", before, 0, revocation.reason, "effect_revoked")

    host.change_policy_state(epoch=6, revoked=False)
    before = count()
    unknown_action = replace(original, operation_id="acs-lost-response", delta=3)
    unknown_grant = await host.authorize(unknown_action)
    lost_reply = await host.dispatch(
        url, unknown_action, unknown_grant, drop_reply_after_commit=True
    )
    record("ACS-05-commit-response-lost", before, 1, lost_reply.status, "unknown")

    before = count()
    retry = await host.dispatch(url, unknown_action, unknown_grant)
    record("ACS-06-idempotent-retry", before, 0, retry.status, "deduplicated")

    before = count()
    code, reply = post_commit(url, forbidden)
    record("ACS-07-unmediated-bypass", before, 1,
           f"http_{code}:{reply.get('status')}", "http_200:committed")

    return {
        "protocol": "acs-agent-effect-study-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "pass" if all(case["pass"] for case in cases) else "fail",
        "cases": cases,
        "case_count": len(cases),
        "upstream": {
            "package": "agent-control-spec",
            "version": acs_version,
            "policy_backend": "Cedar",
            "agent_hooks": "ENFORCE",
            "legacy_alpha4_principal_projection": True,
            "manifest_sha256": host.manifest_sha256,
            "cedar_policy_sha256": host.cedar_sha256,
        },
        "target": {
            "commits": count(),
            "balances": read_target(url, "state")["balances"],
            "journal_operation_ids": [
                item["operation_id"] for item in read_target(url, "journal")["effects"]
            ],
        },
        "limits": (
            "Cooperative host, unauthenticated policy inputs, local disposable HTTP target, "
            "no complete mediation or independent cryptographic attestation. "
            "Expected bypass is a reference-model negative control, not an AGT exploit."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pinned ACS Cedar effect study")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "tests/fixtures/acs_effect/manifest.yaml"
    # Installed sources may be in site-packages; check against a repository checkout
    # and require an explicit visible fixture rather than guessing any other policy.
    if not manifest.is_file():
        raise SystemExit("ACS fixtures not found alongside repository checkout")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="pcs-acs-study-") as temp,
        disposable_target(Path(temp) / "target.sqlite3") as url,
    ):
        result = asyncio.run(run_acs_study(manifest, url))
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{result['status']}: {result['case_count']} real ACS Cedar cases -> {args.out}")
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
