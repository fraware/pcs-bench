"""Real Ed25519 positive and adversarial wire tests, without producer helpers.

Test generation deliberately uses cryptography directly and its own explicit
wire encoder. No source from the experimental signer / issuer / target is
imported. These tests prove only cryptographic assertion appraisal, not ACS
execution, nonce replay prevention, trusted time or committed external effects.
"""
from __future__ import annotations

import base64
import copy
import json
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.independent_ed25519 import (
    ActorTrust,
    IssuerTrust,
    Outcome,
    VerificationContext,
    verify_pair,
)

ACTOR_DOMAIN = b"pcs-bench-ed25519-target-v1\x00"
ISSUER_DOMAIN = b"pcs-bench-issuer-decision-v1\x00"
ACTION_DOMAIN = b"agent-effect-study-action-v1\x00"


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")


def public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def sig(private_key: Ed25519PrivateKey, domain: bytes, value: dict) -> str:
    return base64.urlsafe_b64encode(private_key.sign(domain + canonical(value))).decode().rstrip("=")


@pytest.fixture
def record():
    import hashlib

    actor = Ed25519PrivateKey.generate()
    issuer = Ed25519PrivateKey.generate()
    action = {
        "operation_id": "op-one", "principal": "agent-A", "tenant": "tenant-A",
        "resource": "account:a", "delta": 3,
    }
    digest = hashlib.sha256(ACTION_DOMAIN + canonical(action)).hexdigest()
    statement = {
        "version": "pcs-bench-ed25519-target-v1",
        "audience": "pcs-effect-target:local-1",
        "method": "POST", "path": "/commit",
        "key_id": "actor-A", "nonce": "01" * 16,
        "issued_at": 100, "expires_at": 130, "body": action,
    }
    decision = {
        "version": "pcs-bench-issuer-decision-v1",
        "issuer_id": "issuer-A", "audience": "pcs-effect-target:local-1",
        "actor_key_id": "actor-A", "principal": "agent-A", "tenant": "tenant-A",
        "action_digest": digest, "policy_sha256": "a" * 64,
        "policy_epoch": 3, "decision_id": "02" * 16,
        "issued_at": 100, "expires_at": 130, "verdict": "allow",
    }
    packet = {
        "actor": {"signed": statement, "signature": sig(actor, ACTOR_DOMAIN, statement)},
        "authorization": {
            "statement": decision, "signature": sig(issuer, ISSUER_DOMAIN, decision),
        },
    }
    trusted = VerificationContext(
        target_audience="pcs-effect-target:local-1",
        policy_sha256="a" * 64, policy_epoch=3, now=105,
        actor_keys={"actor-A": ActorTrust(public(actor), "agent-A", "tenant-A")},
        issuer_keys={"issuer-A": IssuerTrust(public(issuer), "a" * 64)},
    )
    return packet, trusted, actor, issuer


def wire(packet: dict) -> bytes:
    return json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify(record, *, packet=None, trust=None):
    raw, ctx, *_ = record
    return verify_pair(wire(raw if packet is None else packet), ctx if trust is None else trust)


def check_rejection(outcome, reason=None):
    assert outcome.outcome is not Outcome.VERIFIED_ASSERTIONS
    if reason:
        assert outcome.reason == reason
    assert not outcome.can_infer_external_effect
    assert not outcome.can_infer_issuer_executed_policy


def resign(packet, actor, issuer):
    packet["actor"]["signature"] = sig(actor, ACTOR_DOMAIN, packet["actor"]["signed"])
    packet["authorization"]["signature"] = sig(
        issuer, ISSUER_DOMAIN, packet["authorization"]["statement"]
    )


def test_independent_public_keys_verify_both_signatures(record):
    res = verify(record)
    assert res.outcome is Outcome.VERIFIED_ASSERTIONS
    assert res.reason == "signatures_and_bindings_valid"
    assert res.actor_key_id == "actor-A"
    assert res.issuer_id == "issuer-A"
    assert len(res.action_digest) == 64
    assert not res.can_infer_issuer_executed_policy
    assert not res.can_infer_external_effect


@pytest.mark.parametrize("path", [
    ("actor", "signed", "body", "delta"),
    ("actor", "signed", "key_id"),
    ("actor", "signed", "audience"),
    ("actor", "signed", "path"),
    ("actor", "signed", "nonce"),
    ("authorization", "statement", "policy_sha256"),
    ("authorization", "statement", "actor_key_id"),
    ("authorization", "statement", "action_digest"),
    ("authorization", "statement", "policy_epoch"),
    ("authorization", "statement", "decision_id"),
])
def test_mutating_signed_fields_never_yields_positive(record, path):
    packet = copy.deepcopy(record[0])
    obj = packet
    for key in path[:-1]:
        obj = obj[key]
    original = obj[path[-1]]
    obj[path[-1]] = 4 if isinstance(original, int) else "tampered"
    check_rejection(verify(record, packet=packet))


def test_valid_signatures_for_different_actions_do_not_bind(record):
    packet = copy.deepcopy(record[0])
    packet["actor"]["signed"]["body"]["delta"] = 4
    resign(packet, record[2], record[3])
    check_rejection(verify(record, packet=packet), "signed_action_or_identity_mismatch")


def test_signer_can_not_substitute_its_key_for_trusted_issuer(record):
    packet = copy.deepcopy(record[0])
    packet["authorization"]["signature"] = sig(
        record[2], ISSUER_DOMAIN, packet["authorization"]["statement"]
    )
    check_rejection(verify(record, packet=packet), "issuer_signature_invalid")


def test_actor_and_issuer_must_have_distinct_registered_public_keys(record):
    ctx = record[1]
    ctx = replace(ctx, issuer_keys={"issuer-A": IssuerTrust(public(record[2]), "a" * 64)})
    check_rejection(verify(record, trust=ctx), "nonindependent_signing_roots")


@pytest.mark.parametrize("field,changed", [
    ("target_audience", "pcs-effect-target:other"),
    ("policy_sha256", "b" * 64),
    ("policy_epoch", 4),
    ("now", 131),
    ("now", 90),
])
def test_changed_verifier_owned_context_invalidates_claim(record, field, changed):
    ctx = replace(record[1], **{field: changed})
    check_rejection(verify(record, trust=ctx))


def test_unregistered_actor_or_issuer_gives_unknown_not_accept(record):
    ctx = record[1]
    check_rejection(
        verify(record, trust=replace(ctx, actor_keys={})), "unavailable_trusted_key"
    )
    check_rejection(
        verify(record, trust=replace(ctx, issuer_keys={})), "unavailable_trusted_key"
    )


def test_current_revocation_and_key_mismatch_refuse_current_reliance(record):
    ctx = record[1]
    revoked_actor = replace(ctx, actor_keys={
        "actor-A": replace(ctx.actor_keys["actor-A"], active=False)
    })
    check_rejection(verify(record, trust=revoked_actor), "trust_root_revoked")
    revoked_issuer = replace(ctx, issuer_keys={
        "issuer-A": replace(ctx.issuer_keys["issuer-A"], active=False)
    })
    check_rejection(verify(record, trust=revoked_issuer), "trust_root_revoked")


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"other": 1}),
    lambda x: x["actor"]["signed"].update({"spoofed": True}),
    lambda x: x["authorization"]["statement"].update({"spoofed": True}),
    lambda x: x["actor"]["signed"]["body"].update({"writes": []}),
    lambda x: x["actor"]["signed"]["body"].update({"delta": True}),
    lambda x: x["authorization"]["statement"].update({"issued_at": True}),
    lambda x: x["actor"]["signed"].update({"issued_at": True}),
])
def test_signed_wire_schema_is_strict(record, mutate):
    packet = copy.deepcopy(record[0])
    mutate(packet)
    check_rejection(verify(record, packet=packet))


def test_duplicate_json_members_never_produce_a_positive_result(record):
    raw = wire(record[0])
    raw = raw.replace(b'"actor":{', b'"actor":{},"actor":{', 1)
    check_rejection(verify_pair(raw, record[1]), "duplicate_json_member")


@pytest.mark.parametrize("wire_bytes", [
    b"{}", b"null", b"[]", b"\x00", b"", b"NaN",
    b'{"actor":null,"authorization":null}',
    b"[" * 16000, b" " * 32769,
])
def test_corrupt_or_oversized_wire_rejected(record, wire_bytes):
    check_rejection(verify_pair(wire_bytes, record[1]))


def test_identical_wire_with_whitespace_and_key_reordering_verifies(record):
    packet = record[0]
    different_whitespace = json.dumps(packet, indent=3, sort_keys=True).encode("utf-8")
    res = verify_pair(different_whitespace, record[1])
    assert res.outcome is Outcome.VERIFIED_ASSERTIONS


def test_signed_permission_does_not_replay_policy_or_prove_effect(record):
    result = verify(record)
    assert result.outcome is Outcome.VERIFIED_ASSERTIONS
    assert result.can_infer_issuer_executed_policy is False
    assert result.can_infer_external_effect is False


def test_hostile_trusted_clock_configuration_fails_closed(record):
    with pytest.raises(ValueError, match="trusted clock"):
        verify(record, trust=replace(record[1], now=True))


def test_trusted_policy_hash_must_be_valid(record):
    with pytest.raises(ValueError, match="trusted policy"):
        verify(record, trust=replace(record[1], policy_sha256="no"))
