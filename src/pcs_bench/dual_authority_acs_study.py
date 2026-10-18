"""Genuine ACS/Cedar decision issuance with independent signed relying-party appraisal.

The trusted laboratory policy issuer invokes actual ACS, signs an allow only
after a passing decision, and holds an Ed25519 key distinct from the actor's.
A second localhost process verifies both at its own SQLite commit boundary.

The target cannot prove that the policy issuer actually ran ACS; a dishonest
trusted issuer remains a trusted-computing-base counterexample by design.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import select
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.acs_effect_host import AcsEffectHost
from pcs_bench.authenticated_target import register_key, sign_request
from pcs_bench.dual_authority_target import (
    audience,
    initialize,
    register_policy_issuer,
    revoke_policy_issuer,
    sign_decision,
)
from pcs_bench.effect_boundary import Action, read_target
from pcs_bench.guarded_target import operator_update


def raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )


@contextmanager
def laboratory_target(
    database: Path, policy_sha: str,
) -> Iterator[tuple[str, Ed25519PrivateKey, Ed25519PrivateKey, str]]:
    initialize(database)
    actor = Ed25519PrivateKey.generate()
    issuer = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="acs-actor", principal="agent-1", tenant="tenant-a",
        public_key=raw_public(actor),
    )
    register_policy_issuer(
        database, issuer_id="acs-policy-issuer",
        public_key=raw_public(issuer), policy_sha256=policy_sha,
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.dual_authority_target",
         "--database", str(database)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(),
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        if not ready:
            raise RuntimeError("two-root effect target not ready")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"two-root target exited: {process.poll()}")
        url = f"http://127.0.0.1:{json.loads(line)['port']}"
        yield url, actor, issuer, audience(database)
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def send(url: str, route: str, packet: object) -> tuple[int, dict[str, Any]]:
    request = Request(
        url + route, method="POST", data=json.dumps(packet).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read(32768))
    except HTTPError as error:
        return error.code, json.loads(error.read(32768))


def read_decision_journal(url: str) -> list[dict[str, Any]]:
    with urlopen(url + "/decision-journal", timeout=5) as response:
        return json.load(response)["commits"]


async def run_study(
    manifest: Path, url: str, database: Path,
    actor: Ed25519PrivateKey, issuer: Ed25519PrivateKey, aud: str,
) -> dict[str, Any]:
    from agent_control_spec import __version__ as acs_version

    host = AcsEffectHost(manifest, epoch=1, legacy_cedar_principal_bridge=True)
    rows: list[dict[str, Any]] = []

    def effect_count() -> int:
        return len(read_target(url, "journal")["effects"])

    def actor_packet(route: str, body: dict[str, object]) -> dict[str, object]:
        return sign_request(actor, key_id="acs-actor", audience_id=aud,
                            route=route, body=body)

    async def authorize(action: Action) -> bool:
        decision = await host.authorize(action)
        return decision.permitted

    async def issue(action: Action) -> dict[str, object]:
        verdict = await host.authorize(action)
        if not verdict.permitted:
            raise ValueError(f"ACS refused authorization: {verdict.reason}")
        return sign_decision(
            issuer, issuer_id="acs-policy-issuer", target_audience=aud,
            actor_key_id="acs-actor", action=action,
            policy_sha256=host.cedar_sha256, policy_epoch=host.epoch,
        )

    def submit(action: Action, policy_token: dict[str, object] | None) -> tuple[int, dict]:
        packet = actor_packet("/commit", action.to_dict())
        body = (
            {"actor": packet, "authorization": policy_token}
            if policy_token is not None else packet
        )
        return send(url, "/commit", body)

    def add(name: str, before: int, code: int, data: dict, expected: tuple[int, str, int]) -> None:
        status = data.get("status", data.get("error"))
        observed = effect_count() - before
        rows.append({
            "case": name, "actual_http": code, "actual_outcome": status,
            "observed_commits": observed, "expected": list(expected),
            "pass": (code, status, observed) == expected,
        })

    base = Action("dual-acs-valid", "agent-1", "tenant-a", "account:a", 3)
    before = effect_count()
    code, result = submit(base, await issue(base))
    add("DUAL-01-independent-signed-acs-permit", before, code, result, (200, "committed", 1))

    without = replace(base, operation_id="actor-only")
    before = effect_count()
    code, result = submit(without, None)
    add("DUAL-02-actor-only-bypass-blocked", before, code, result,
        (403, "policy_authorization_required", 0))

    too_large = replace(base, operation_id="cedar-deny", delta=60)
    assert not await authorize(too_large)
    before = effect_count()
    code, result = submit(too_large, None)
    add("DUAL-03-acs-denial-has-no-permission", before, code, result,
        (403, "policy_authorization_required", 0))

    original = replace(base, operation_id="argument-mutation")
    signed = await issue(original)
    changed = replace(original, delta=5)
    before = effect_count()
    code, result = submit(changed, signed)
    add("DUAL-04-action-bound-decision", before, code, result,
        (403, "decision_action_mismatch", 0))

    stage_action = replace(base, operation_id="stage-before-revocation")
    scode, stage = send(url, "/stage", actor_packet("/stage", stage_action.to_dict()))
    if scode != 202:
        raise RuntimeError(f"target staging unexpectedly failed: {stage}")
    stage_token = await issue(stage_action)
    operator_update(database, next_epoch=2, revoked=True)
    stage_finish = {
        "operation_id": stage_action.operation_id,
        "request_digest": stage["request_digest"],
    }
    before = effect_count()
    code, result = send(url, "/commit-staged", {
        "actor": actor_packet("/commit-staged", stage_finish),
        "authorization": stage_token,
    })
    add("DUAL-05-revocation-after-staging", before, code, result,
        (409, "authorization_policy_epoch_stale", 0))

    operator_update(database, next_epoch=3, revoked=False)
    host.change_policy_state(epoch=3, revoked=False)
    regranted = replace(base, operation_id="new-policy-epoch")
    before = effect_count()
    code, result = submit(regranted, await issue(regranted))
    add("DUAL-06-new-policy-epoch-commit", before, code, result,
        (200, "committed", 1))

    # A malicious/compromised *trusted* issuer can produce a syntactically
    # valid allow without calling ACS: the target cannot attest issuer conduct.
    fabricated = replace(base, operation_id="issuer-assumption-negative")
    issuer_token = sign_decision(
        issuer, issuer_id="acs-policy-issuer", target_audience=aud,
        actor_key_id="acs-actor", action=fabricated,
        policy_sha256=host.cedar_sha256, policy_epoch=host.epoch,
    )
    before = effect_count()
    code, result = submit(fabricated, issuer_token)
    add("DUAL-07-honest-issuer-assumption", before, code, result,
        (200, "committed", 1))

    revoke_policy_issuer(database, "acs-policy-issuer")
    denied_after_revocation = replace(base, operation_id="revoked-policy-key")
    before = effect_count()
    code, result = submit(denied_after_revocation, await issue(denied_after_revocation))
    add("DUAL-08-revoked-policy-signer", before, code, result,
        (403, "actor_or_issuer_revoked", 0))

    commitments = await asyncio.to_thread(read_decision_journal, url)
    return {
        "protocol": "pcs-two-root-acs-experiment-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pass" if all(x["pass"] for x in rows) else "fail",
        "case_count": len(rows),
        "cases": rows,
        "acs_version": acs_version,
        "policy_sha256": host.cedar_sha256,
        "manifest_sha256": host.manifest_sha256,
        "target": {
            "authenticated_commits": len(commitments),
            "balances": read_target(url, "state")["balances"],
            "issuer_ids": sorted({c["issuer_id"] for c in commitments}),
        },
        "limit": (
            "Signing key separation and target appraisal prove neither that ACS was "
            "actually executed before a token was minted, nor complete host mediation, "
            "independent key custody, trusted issuer governance or remote attestation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real ACS with two-root target appraisal")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "tests/fixtures/acs_effect/manifest.yaml"
    if not manifest.is_file():
        raise SystemExit("requires ACS fixture from editable checkout")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    host = AcsEffectHost(manifest, epoch=1, legacy_cedar_principal_bridge=True)
    with (
        tempfile.TemporaryDirectory(prefix="dual-root-acs-") as temp,
        laboratory_target(Path(temp) / "target.sqlite3", host.cedar_sha256)
        as (url, actor, issuer, aud),
    ):
        result = asyncio.run(
            run_study(manifest, url, Path(temp) / "target.sqlite3", actor, issuer, aud)
        )
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{result['status']}: {result['case_count']} ACS+two-root target cases")
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
