"""Cross-producer compatibility with an IMMUTABLY pinned, independent checkout.

The isolated child imports experimental producer sign_request/sign_decision
from a different source checkout at the exact reviewed research SHA.
The parent imports only the independent verifier from this checkout. No
signing function or serialization helper is shared between these processes.

Skipped when the external reference checkout is absent; dedicated CI MUST
provision it and set PCS_PINNED_PRODUCER for this test to become mandatory.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pcs_bench.independent_ed25519 import (
    ActorTrust,
    IssuerTrust,
    Outcome,
    VerificationContext,
    verify_pair,
)

PINNED = "423aa6d8682117474b22dd960da62b490f148361"
SOURCE_SCRIPT = r"""
import base64
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pcs_bench.authenticated_target import sign_request
from pcs_bench.dual_authority_target import sign_decision
from pcs_bench.effect_boundary import Action

actor = Ed25519PrivateKey.generate()
issuer = Ed25519PrivateKey.generate()
a = Action("cross-implementation", "agent-A", "tenant-A", "account:a", 3)
actor_packet = sign_request(
    actor, key_id="actor-A", audience_id="pcs-effect-target:cross-study",
    route="/commit", body=a.to_dict(),
    issued_at=100, expires_at=130, nonce="01" * 16,
)
issuer_packet = sign_decision(
    issuer, issuer_id="issuer-A", target_audience="pcs-effect-target:cross-study",
    actor_key_id="actor-A", action=a, policy_sha256="a" * 64, policy_epoch=3,
    issued_at=100, expires_at=130, decision_id="02" * 16,
)
def public(k):
    return base64.b64encode(k.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode("ascii")

print(json.dumps({
    "pair": {"actor": actor_packet, "authorization": issuer_packet},
    "actor_public": public(actor), "issuer_public": public(issuer),
}))
"""


def test_separate_pinned_producer_signatures_verify_without_importing_producer_helpers():
    path = os.getenv("PCS_PINNED_PRODUCER")
    if not path:
        pytest.skip("requires separate checkout pinned by dedicated workflow")
    producer = Path(path).resolve(strict=True)
    sha = subprocess.run(
        ["git", "-C", str(producer), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    assert sha == PINNED, "producer evidence source does not match frozen SHA"
    env = {**os.environ, "PYTHONPATH": str(producer / "src")}
    child = subprocess.run(
        [sys.executable, "-c", SOURCE_SCRIPT],
        cwd=producer, env=env, capture_output=True,
        text=True, check=True, timeout=15,
    )
    fixture = json.loads(child.stdout)
    trusted = VerificationContext(
        target_audience="pcs-effect-target:cross-study",
        policy_sha256="a" * 64, policy_epoch=3, now=105,
        actor_keys={"actor-A": ActorTrust(
            base64.b64decode(fixture["actor_public"], validate=True),
            "agent-A", "tenant-A",
        )},
        issuer_keys={"issuer-A": IssuerTrust(
            base64.b64decode(fixture["issuer_public"], validate=True), "a" * 64,
        )},
    )
    packet = fixture["pair"]
    result = verify_pair(json.dumps(packet, separators=(",", ":")).encode(), trusted)
    assert result.outcome is Outcome.VERIFIED_ASSERTIONS
    assert result.action_digest == packet["authorization"]["statement"]["action_digest"]
    assert result.can_infer_external_effect is False
    assert result.can_infer_issuer_executed_policy is False

    # Consumer-side mutation must invalidate the producer's real signatures.
    packet["actor"]["signed"]["body"]["delta"] = 4
    outcome = verify_pair(json.dumps(packet).encode(), trusted)
    assert outcome.outcome is Outcome.REFUTED
