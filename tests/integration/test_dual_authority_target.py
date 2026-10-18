"""Adversarial two-root authorization tests against a separate HTTP/SQLite target.

A valid signed actor alone has no route to an effect. Policy tokens are issued
by a distinct Ed25519 key and must be appraised at the atomic commit boundary.
These tests do not establish that the trusted issuer actually consulted ACS.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.authenticated_target import register_key, revoke_key, sign_request
from pcs_bench.dual_authority_target import (
    audience,
    initialize,
    register_policy_issuer,
    revoke_policy_issuer,
    sign_decision,
)
from pcs_bench.effect_boundary import Action, read_target
from pcs_bench.guarded_target import operator_update

POLICY_SHA = "a" * 64


def raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )


@contextmanager
def target_server(tmp_path: Path):
    db = tmp_path / "dual-authority.sqlite3"
    initialize(db)
    actor_key = Ed25519PrivateKey.generate()
    issuer_key = Ed25519PrivateKey.generate()
    register_key(db, key_id="actor-one", principal="agent-1",
                 tenant="tenant-a", public_key=raw_public(actor_key))
    register_policy_issuer(db, issuer_id="cedar-policy-issuer",
                           public_key=raw_public(issuer_key), policy_sha256=POLICY_SHA)
    p = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.dual_authority_target", "--database", str(db)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(),
    )
    try:
        assert p.stdout is not None
        ready, _, _ = select.select([p.stdout], [], [], 15)
        assert ready, "target failed to start"
        line = p.stdout.readline()
        assert line, "target process terminated before ready"
        url = f"http://127.0.0.1:{json.loads(line)['port']}"
        assert audience(db)
        yield (url, db, actor_key, issuer_key, audience(db))
    finally:
        p.terminate()
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate(timeout=5)


@pytest.fixture
def target(tmp_path: Path):
    with target_server(tmp_path) as ctx:
        yield ctx


def action(operation_id: str = "test-operation", **kwargs: object) -> Action:
    return replace(
        Action(operation_id, "agent-1", "tenant-a", "account:a", 3), **kwargs,
    )


def send(url: str, route: str, packet: object) -> tuple[int, dict]:
    req = Request(url + route, method="POST", data=json.dumps(packet).encode(),
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as result:
            return result.status, json.load(result)
    except HTTPError as error:
        return error.code, json.load(error)


def signed_actor(
    ctx, route: str, body: dict[str, object], *,
    key: Ed25519PrivateKey | None = None, key_id: str = "actor-one",
) -> dict[str, object]:
    _, _, original, _, aud = ctx
    return sign_request(key or original, key_id=key_id, audience_id=aud,
                        route=route, body=body)


def signed_decision(
    ctx, act: Action, *,
    signer: Ed25519PrivateKey | None = None,
    issuer: str = "cedar-policy-issuer",
    actor_key_id: str = "actor-one",
    policy_sha: str = POLICY_SHA,
    epoch: int = 1,
    **kwargs,
) -> dict[str, object]:
    _, _, _, original, aud = ctx
    return sign_decision(
        signer or original, issuer_id=issuer, target_audience=aud,
        actor_key_id=actor_key_id, action=act, policy_sha256=policy_sha,
        policy_epoch=epoch, **kwargs,
    )


def commit(ctx, act: Action, *, decision: dict | None = None,
           actor: dict | None = None, route: str = "/commit") -> tuple[int, dict]:
    a = actor or signed_actor(ctx, route, act.to_dict())
    token = decision or signed_decision(ctx, act)
    return send(ctx[0], route, {"actor": a, "authorization": token})


def journal(ctx) -> list[dict]:
    return read_target(ctx[0], "journal")["effects"]


def test_independently_signed_allow_and_actor_commit_one_effect(target):
    code, receipt = commit(target, action())
    assert (code, receipt["status"]) == (200, "committed")
    assert read_target(target[0], "state")["balances"] == {"account:a": 3}
    with urlopen(target[0] + "/decision-journal") as response:
        entries = json.load(response)["commits"]
    assert len(entries) == 1
    assert entries[0]["issuer_id"] == "cedar-policy-issuer"
    assert entries[0]["actor_key_id"] == "actor-one"
    assert len(entries[0]["decision_id"]) == 32


def test_valid_actor_without_policy_credential_cannot_commit(target):
    packet = signed_actor(target, "/commit", action().to_dict())
    code, response = send(target[0], "/commit", packet)
    assert (code, response["error"]) == (403, "policy_authorization_required")
    assert journal(target) == []


def test_unregistered_or_actor_self_signed_policy_is_rejected(target):
    act = action()
    forged = signed_decision(target, act, signer=target[2])
    code, r = commit(target, act, decision=forged)
    assert (code, r["error"]) == (401, "invalid_actor_or_issuer_signature")
    unknown = signed_decision(target, act, issuer="missing-issuer")
    code, r = commit(target, act, decision=unknown)
    assert (code, r["error"]) == (401, "untrusted_actor_or_issuer")
    assert journal(target) == []


def test_same_registered_public_key_cannot_be_both_actor_and_issuer(target):
    register_policy_issuer(
        target[1], issuer_id="wrongly-shared-key",
        public_key=raw_public(target[2]), policy_sha256=POLICY_SHA,
    )
    act = action()
    credential = signed_decision(
        target, act, signer=target[2], issuer="wrongly-shared-key",
    )
    code, result = commit(target, act, decision=credential)
    assert (code, result["error"]) == (403, "independent_signer_required")
    assert journal(target) == []


def test_decision_is_bound_to_actor_key_and_identity(target):
    act = action()
    mismatched = signed_decision(target, act, actor_key_id="another-actor")
    code, r = commit(target, act, decision=mismatched)
    assert (code, r["error"]) == (403, "decision_actor_key_mismatch")
    other = replace(act, principal="other-principal")
    code, r = commit(target, other, decision=signed_decision(target, other))
    assert (code, r["error"]) == (403, "decision_identity_mismatch")
    assert journal(target) == []


def test_changed_action_after_issuer_signature_fails_closed(target):
    authorized = action()
    changed = replace(authorized, delta=4)
    code, r = commit(target, changed, decision=signed_decision(target, authorized))
    assert (code, r["error"]) == (403, "decision_action_mismatch")
    assert journal(target) == []


def test_tampered_issuer_token_and_untrusted_policy_digest_fail(target):
    act = action()
    token = signed_decision(target, act)
    token["statement"]["expires_at"] += 1
    code, r = commit(target, act, decision=token)
    assert (code, r["error"]) == (401, "invalid_actor_or_issuer_signature")
    token = signed_decision(target, act, policy_sha="b" * 64)
    code, r = commit(target, act, decision=token)
    assert (code, r["error"]) == (403, "policy_digest_not_trusted")
    assert journal(target) == []


def test_expired_and_wrong_audience_authority_fail(target):
    act = action()
    now = int(time.time())
    token = signed_decision(target, act, issued_at=now - 50, expires_at=now - 20)
    code, r = commit(target, act, decision=token)
    assert (code, r["error"]) == (401, "expired_or_future_authority")
    token = signed_decision(target, act)
    token["statement"]["audience"] = "some-other-target"
    code, r = commit(target, act, decision=token)
    assert (code, r["error"]) == (401, "wrong_target_audience")
    assert journal(target) == []


def test_revocation_of_policy_issuer_prevents_new_commit(target):
    revoke_policy_issuer(target[1], "cedar-policy-issuer")
    code, r = commit(target, action())
    assert (code, r["error"]) == (403, "actor_or_issuer_revoked")
    assert journal(target) == []


def test_revocation_of_actor_key_prevents_new_commit(target):
    revoke_key(target[1], key_id="actor-one")
    code, r = commit(target, action())
    assert (code, r["error"]) == (403, "actor_or_issuer_revoked")
    assert journal(target) == []


def test_target_policy_revocation_after_decision_prevents_commit(target):
    act = action()
    decision = signed_decision(target, act)
    operator_update(target[1], next_epoch=2, revoked=True)
    code, r = commit(target, act, decision=decision)
    assert (code, r["error"]) == (409, "authorization_policy_epoch_stale")
    assert journal(target) == []


def test_still_allowed_policy_epoch_change_invalidates_decision(target):
    act = action()
    decision = signed_decision(target, act)
    operator_update(target[1], next_epoch=2, revoked=False)
    code, r = commit(target, act, decision=decision)
    assert (code, r["error"]) == (409, "authorization_policy_epoch_stale")
    assert journal(target) == []


def test_target_policy_denies_even_with_signed_allow_from_issuer(target):
    act = action(delta=55)
    code, r = commit(target, act)
    assert (code, r["error"]) == (403, "amount_not_granted")
    assert journal(target) == []


def test_actor_nonce_replay_fails_but_fresh_nonce_idempotently_deduplicates(target):
    act = action()
    actor = signed_actor(target, "/commit", act.to_dict())
    decision = signed_decision(target, act)
    assert commit(target, act, actor=actor, decision=decision)[1]["status"] == "committed"
    code, r = commit(target, act, actor=actor, decision=decision)
    assert (code, r["error"]) == (409, "actor_nonce_replayed")
    code, r = commit(target, act, decision=decision)
    assert (code, r["status"]) == (200, "deduplicated")
    assert len(journal(target)) == 1


def test_valid_registered_actor_cannot_reuse_others_decision(target):
    act = action()
    second = Ed25519PrivateKey.generate()
    register_key(
        target[1], key_id="actor-two", principal="agent-1", tenant="tenant-a",
        public_key=raw_public(second),
    )
    actor = signed_actor(target, "/commit", act.to_dict(), key=second, key_id="actor-two")
    code, r = commit(target, act, actor=actor)
    assert (code, r["error"]) == (403, "decision_actor_key_mismatch")
    assert journal(target) == []


def test_staged_action_requires_policy_decision_at_final_commit(target):
    act = action()
    stage_packet = signed_actor(target, "/stage", act.to_dict())
    code, staged = send(target[0], "/stage", stage_packet)
    assert (code, staged["status"]) == (202, "staged")
    assert journal(target) == []
    body = {"operation_id": act.operation_id, "request_digest": staged["request_digest"]}
    actor = signed_actor(target, "/commit-staged", body)
    code, r = send(target[0], "/commit-staged", actor)
    assert (code, r["error"]) == (403, "policy_authorization_required")
    code, r = send(target[0], "/commit-staged", {
        "actor": actor, "authorization": signed_decision(target, act),
    })
    assert (code, r["status"]) == (200, "committed")
    assert len(journal(target)) == 1


def test_policy_changed_after_stage_blocks_new_commit(target):
    act = action()
    code, staged = send(
        target[0], "/stage", signed_actor(target, "/stage", act.to_dict()),
    )
    assert code == 202
    operator_update(target[1], next_epoch=2, revoked=True)
    operator_update(target[1], next_epoch=3, revoked=False)
    body = {"operation_id": act.operation_id, "request_digest": staged["request_digest"]}
    code, r = send(target[0], "/commit-staged", {
        "actor": signed_actor(target, "/commit-staged", body),
        "authorization": signed_decision(target, act, epoch=3),
    })
    assert (code, r["error"]) == (409, "staged_policy_epoch_stale")
    assert journal(target) == []


def test_second_key_cannot_commit_first_keys_stage(target):
    act = action()
    code, staged = send(
        target[0], "/stage", signed_actor(target, "/stage", act.to_dict()),
    )
    assert code == 202
    second = Ed25519PrivateKey.generate()
    register_key(
        target[1], key_id="actor-two", principal="agent-1", tenant="tenant-a",
        public_key=raw_public(second),
    )
    body = {"operation_id": act.operation_id, "request_digest": staged["request_digest"]}
    code, r = send(target[0], "/commit-staged", {
        "actor": signed_actor(target, "/commit-staged", body,
                              key=second, key_id="actor-two"),
        "authorization": signed_decision(target, act, actor_key_id="actor-two"),
    })
    assert (code, r["error"]) == (403, "stage_actor_key_mismatch")
    assert journal(target) == []


def test_concurrent_double_signature_requests_commit_once(target):
    act = action()
    token = signed_decision(target, act)
    actor = signed_actor(target, "/commit", act.to_dict())
    packet = {"actor": actor, "authorization": token}
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: send(target[0], "/commit", packet), range(16)))
    assert sum(result.get("status") == "committed" for _, result in results) == 1
    assert sum(result.get("error") == "actor_nonce_replayed" for _, result in results) == 15
    assert len(journal(target)) == 1


def test_policy_decision_id_reuse_for_different_operation_is_rejected(target):
    ident = "1" * 32
    first = action("op-first")
    second = action("op-second")
    token = signed_decision(target, first, decision_id=ident)
    assert commit(target, first, decision=token)[1]["status"] == "committed"
    alternate = signed_decision(target, second, decision_id=ident)
    code, result = commit(target, second, decision=alternate)
    assert (code, result["error"]) == (409, "decision_id_reused")
    assert len(journal(target)) == 1
