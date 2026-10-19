"""Independent Ed25519 evidence appraisal for the PCS experimental wire profile.

This module does NOT import PCS experiment signing helpers, authorize a tool,
replay Cedar, authenticate an issuer's software execution, validate nonce
uniqueness, or verify a target effect. It establishes only whether two
cryptographic assertions are authentic and mutually consistent relative to
verifier-owned trust roots at a specified appraisal time.

Wire compatibility profile: actor v1 and issuer-decision v1, with their
distinct domain-separated sorted-key JSON encodings. NOT RFC 8785 JCS.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ACTOR_VERSION = "pcs-bench-ed25519-target-v1"
ISSUER_VERSION = "pcs-bench-issuer-decision-v1"
ACTION_DOMAIN = b"agent-effect-study-action-v1\x00"
ACTOR_DOMAIN = b"pcs-bench-ed25519-target-v1\x00"
ISSUER_DOMAIN = b"pcs-bench-issuer-decision-v1\x00"
MAX_WIRE_BYTES = 32768
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")


class Outcome(str, Enum):
    VERIFIED_ASSERTIONS = "verified_assertions"
    REFUTED = "refuted"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class ActorTrust:
    public_key: bytes
    principal: str
    tenant: str
    active: bool = True


@dataclass(frozen=True)
class IssuerTrust:
    public_key: bytes
    policy_sha256: str
    active: bool = True


@dataclass(frozen=True)
class VerificationContext:
    """Privately configured by relying-party operator, never from evidence."""

    target_audience: str
    policy_sha256: str
    policy_epoch: int
    now: int
    actor_keys: Mapping[str, ActorTrust]
    issuer_keys: Mapping[str, IssuerTrust]


@dataclass(frozen=True)
class Assessment:
    outcome: Outcome
    reason: str
    action_digest: str | None = None
    actor_key_id: str | None = None
    issuer_id: str | None = None

    @property
    def can_infer_external_effect(self) -> bool:
        """A signed assertion is never an independent target observation."""
        return False

    @property
    def can_infer_issuer_executed_policy(self) -> bool:
        """Signing a decision cannot attest how the signer produced it."""
        return False


class _BadWire(ValueError):
    pass


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise _BadWire("duplicate_json_member")
        output[key] = value
    return output


def _reject_constant(_value: str) -> None:
    raise _BadWire("non_finite_number")


def _bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _keys(value: object, required: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == required


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", value):
        raise _BadWire("invalid_signature_encoding")
    try:
        raw = base64.b64decode(value + "==", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise _BadWire("invalid_signature_encoding") from exc
    if len(raw) != 64 or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
        raise _BadWire("noncanonical_signature_encoding")
    return raw


def _valid_public_key(data: object) -> bool:
    return isinstance(data, bytes) and len(data) == 32


def _action(value: object) -> str:
    if not _keys(value, {"operation_id", "principal", "tenant", "resource", "delta"}):
        raise _BadWire("invalid_action_schema")
    assert isinstance(value, dict)
    if any(not isinstance(value[k], str) or not value[k] for k in (
        "operation_id", "principal", "tenant", "resource"
    )):
        raise _BadWire("invalid_action_identity")
    if type(value["delta"]) is not int:
        raise _BadWire("invalid_action_delta")
    return hashlib.sha256(ACTION_DOMAIN + _bytes(value)).hexdigest()


def _time_ok(s: dict[str, object], now: int) -> bool:
    start, end = s["issued_at"], s["expires_at"]
    return (
        type(start) is int and type(end) is int
        and 0 < end - start <= 60
        and start <= now + 5
        and end >= now
    )


def _verify(pub: bytes, signature: bytes, content: bytes) -> bool:
    if not _valid_public_key(pub):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(signature, content)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def _appraise(packet: dict[str, object], ctx: VerificationContext) -> Assessment:
    actor = packet["actor"]
    issuer = packet["authorization"]
    if not _keys(actor, {"signed", "signature"}):
        raise _BadWire("invalid_actor_envelope")
    if not _keys(issuer, {"statement", "signature"}):
        raise _BadWire("invalid_issuer_envelope")
    assert isinstance(actor, dict) and isinstance(issuer, dict)
    a = actor["signed"]
    d = issuer["statement"]
    if not _keys(a, {
        "version", "audience", "method", "path", "key_id", "nonce",
        "issued_at", "expires_at", "body",
    }):
        raise _BadWire("invalid_actor_statement")
    if not _keys(d, {
        "version", "issuer_id", "audience", "actor_key_id", "principal", "tenant",
        "action_digest", "policy_sha256", "policy_epoch", "decision_id",
        "issued_at", "expires_at", "verdict",
    }):
        raise _BadWire("invalid_issuer_statement")
    assert isinstance(a, dict) and isinstance(d, dict)
    if a["version"] != ACTOR_VERSION or d["version"] != ISSUER_VERSION:
        raise _BadWire("unsupported_wire_profile")
    if a["method"] != "POST" or a["path"] != "/commit" or d["verdict"] != "allow":
        raise _BadWire("wrong_route_or_verdict")
    if not isinstance(a["key_id"], str) or not IDENTIFIER.fullmatch(a["key_id"]):
        raise _BadWire("invalid_actor_key_id")
    if not isinstance(d["issuer_id"], str) or not IDENTIFIER.fullmatch(d["issuer_id"]):
        raise _BadWire("invalid_issuer_id")
    if not isinstance(a["nonce"], str) or not HEX32.fullmatch(a["nonce"]):
        raise _BadWire("invalid_actor_nonce")
    if not isinstance(d["decision_id"], str) or not HEX32.fullmatch(d["decision_id"]):
        raise _BadWire("invalid_decision_id")
    if not isinstance(d["action_digest"], str) or not HEX64.fullmatch(d["action_digest"]):
        raise _BadWire("invalid_action_hash")
    if not isinstance(d["policy_sha256"], str) or not HEX64.fullmatch(d["policy_sha256"]):
        raise _BadWire("invalid_policy_hash")
    if type(d["policy_epoch"]) is not int or d["policy_epoch"] < 1:
        raise _BadWire("invalid_policy_epoch")
    if not isinstance(d["principal"], str) or not d["principal"]:
        raise _BadWire("invalid_principal")
    if not isinstance(d["tenant"], str) or not d["tenant"]:
        raise _BadWire("invalid_tenant")
    if not isinstance(d["actor_key_id"], str) or not IDENTIFIER.fullmatch(d["actor_key_id"]):
        raise _BadWire("invalid_decision_actor")
    if not _time_ok(a, ctx.now) or not _time_ok(d, ctx.now):
        return Assessment(Outcome.REFUTED, "credential_not_current")
    if a["audience"] != ctx.target_audience or d["audience"] != ctx.target_audience:
        return Assessment(Outcome.REFUTED, "wrong_target_audience")
    actor_key = ctx.actor_keys.get(a["key_id"])
    issuer_key = ctx.issuer_keys.get(d["issuer_id"])
    if actor_key is None or issuer_key is None:
        return Assessment(Outcome.UNDETERMINED, "unavailable_trusted_key")
    if not actor_key.active or not issuer_key.active:
        return Assessment(Outcome.REFUTED, "trust_root_revoked")
    if actor_key.public_key == issuer_key.public_key:
        return Assessment(Outcome.REFUTED, "nonindependent_signing_roots")
    if not _valid_public_key(actor_key.public_key) or not _valid_public_key(
        issuer_key.public_key
    ):
        return Assessment(Outcome.UNDETERMINED, "invalid_verifier_owned_key")
    if not _verify(
        actor_key.public_key, _signature(actor["signature"]), ACTOR_DOMAIN + _bytes(a)
    ):
        return Assessment(Outcome.REFUTED, "actor_signature_invalid")
    if not _verify(
        issuer_key.public_key, _signature(issuer["signature"]), ISSUER_DOMAIN + _bytes(d)
    ):
        return Assessment(Outcome.REFUTED, "issuer_signature_invalid")
    digest = _action(a["body"])
    assert isinstance(a["body"], dict)
    if (
        a["key_id"] != d["actor_key_id"]
        or a["body"]["principal"] != actor_key.principal
        or a["body"]["tenant"] != actor_key.tenant
        or d["principal"] != actor_key.principal
        or d["tenant"] != actor_key.tenant
        or d["action_digest"] != digest
    ):
        return Assessment(Outcome.REFUTED, "signed_action_or_identity_mismatch")
    if (
        d["policy_sha256"] != ctx.policy_sha256
        or d["policy_sha256"] != issuer_key.policy_sha256
        or d["policy_epoch"] != ctx.policy_epoch
    ):
        return Assessment(Outcome.REFUTED, "policy_authority_mismatch")
    return Assessment(
        Outcome.VERIFIED_ASSERTIONS, "signatures_and_bindings_valid",
        action_digest=digest, actor_key_id=a["key_id"], issuer_id=d["issuer_id"],
    )


def verify_pair(raw: bytes, context: VerificationContext) -> Assessment:
    """Appraise two assertions under an independently provisioned trust context."""
    if type(context.now) is not int or context.now < 0:
        raise ValueError("trusted clock must be a nonnegative integer")
    if not isinstance(context.target_audience, str) or not context.target_audience:
        raise ValueError("trusted audience is required")
    if not isinstance(context.policy_sha256, str) or not HEX64.fullmatch(
        context.policy_sha256
    ):
        raise ValueError("trusted policy digest is invalid")
    if type(context.policy_epoch) is not int or context.policy_epoch < 1:
        raise ValueError("trusted policy epoch is invalid")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_WIRE_BYTES:
        return Assessment(Outcome.REFUTED, "invalid_wire_size")
    try:
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
        if not _keys(value, {"actor", "authorization"}):
            raise _BadWire("invalid_pair_schema")
        assert isinstance(value, dict)
        return _appraise(value, context)
    except (_BadWire, TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        return Assessment(Outcome.REFUTED, str(exc) or "invalid_signed_wire")
