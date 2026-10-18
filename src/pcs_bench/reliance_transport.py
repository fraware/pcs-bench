"""Conservative, verifier-relative transport of agent effect evidence.

No cryptographic signature, Cedar replay, issuer execution, or effect is
verified *by this module*. Those checks MUST be independently implemented by
trusted, locally configured verifier callbacks. Claim-provided "verified"
flags are never inspected. An old positive result is not transported to a
new policy/key/verifier context without running the current checkers.

This is a typed reference acceptance contract, not a proof of the callbacks,
a security certification, or a replacement for an enforcement mechanism.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

DOMAIN = b"pcs-reliance-transport-v1\x00"
REQUIRED = (
    "actor_signature",
    "issuer_signature",
    "policy_result",
    "issuer_execution",
    "effect_observation",
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:/-]{1,128}\Z")


class Outcome(str, Enum):
    ESTABLISHED = "established"
    REFUTED = "refuted"
    UNKNOWN = "unknown"


class Disposition(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class VerifierSpec:
    check: str
    verifier_id: str
    version: str

    def __post_init__(self) -> None:
        if self.check not in REQUIRED:
            raise ValueError("unrecognized verifier check")
        if not _IDENTIFIER.fullmatch(self.verifier_id) or not _IDENTIFIER.fullmatch(
            self.version
        ):
            raise ValueError("invalid verifier identity or version")


@dataclass(frozen=True, slots=True)
class Claim:
    operation_id: str
    action_digest: str
    target_audience: str
    policy_sha256: str
    policy_epoch: int
    actor_key_sha256: str
    issuer_key_sha256: str
    effect_receipt_digest: str
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.operation_id) or not _IDENTIFIER.fullmatch(
            self.target_audience
        ):
            raise ValueError("invalid operation or target identity")
        for name in (
            "action_digest",
            "policy_sha256",
            "actor_key_sha256",
            "issuer_key_sha256",
            "effect_receipt_digest",
        ):
            if not _HEX64.fullmatch(getattr(self, name)):
                raise ValueError(f"invalid digest: {name}")
        if type(self.policy_epoch) is not int or self.policy_epoch < 1:
            raise ValueError("invalid policy epoch")
        if (
            type(self.issued_at) is not int
            or type(self.expires_at) is not int
            or self.issued_at < 0
            or self.expires_at <= self.issued_at
        ):
            raise ValueError("invalid validity interval")


@dataclass(frozen=True, slots=True)
class CurrentTrust:
    action_digest: str
    target_audience: str
    policy_sha256: str
    policy_epoch: int
    actor_key_sha256: str
    issuer_key_sha256: str
    observation_source: str
    checkers: tuple[VerifierSpec, ...]

    def __post_init__(self) -> None:
        for name in (
            "action_digest",
            "policy_sha256",
            "actor_key_sha256",
            "issuer_key_sha256",
        ):
            if not _HEX64.fullmatch(getattr(self, name)):
                raise ValueError(f"invalid trust digest: {name}")
        if not _IDENTIFIER.fullmatch(self.target_audience) or not _IDENTIFIER.fullmatch(
            self.observation_source
        ):
            raise ValueError("invalid trusted context identity")
        if type(self.policy_epoch) is not int or self.policy_epoch < 1:
            raise ValueError("invalid trusted policy epoch")
        if self.actor_key_sha256 == self.issuer_key_sha256:
            raise ValueError("actor and issuer trust keys must be distinct")
        checks = [s.check for s in self.checkers]
        if len(checks) != len(set(checks)):
            raise ValueError("ambiguous duplicate verifier specification")
        if set(checks) != set(REQUIRED):
            raise ValueError("each assurance obligation requires a verifier specification")
        # A policy replay and evidence of *actual issuer execution* must be
        # independently sourced, even if they use the same policy semantics.
        sources = {s.check: s.verifier_id for s in self.checkers}
        if sources["policy_result"] == sources["issuer_execution"]:
            raise ValueError("policy replay and execution witness must be distinct")

    @property
    def digest(self) -> str:
        fields = {
            "action_digest": self.action_digest,
            "target_audience": self.target_audience,
            "policy_sha256": self.policy_sha256,
            "policy_epoch": self.policy_epoch,
            "actor_key_sha256": self.actor_key_sha256,
            "issuer_key_sha256": self.issuer_key_sha256,
            "observation_source": self.observation_source,
            "checkers": [
                {"check": item.check, "verifier_id": item.verifier_id, "version": item.version}
                for item in sorted(self.checkers, key=lambda item: item.check)
            ],
        }
        return hashlib.sha256(DOMAIN + _json(fields)).hexdigest()


@dataclass(frozen=True, slots=True)
class CheckResult:
    outcome: Outcome
    verifier_id: str
    verifier_version: str
    claim_binding: str

    def __post_init__(self) -> None:
        if type(self.outcome) is not Outcome:
            raise ValueError("invalid check outcome")
        if not _IDENTIFIER.fullmatch(self.verifier_id) or not _IDENTIFIER.fullmatch(
            self.verifier_version
        ):
            raise ValueError("invalid returned verifier metadata")
        if not _HEX64.fullmatch(self.claim_binding):
            raise ValueError("invalid returned claim binding")


@dataclass(frozen=True, slots=True)
class Appraisal:
    disposition: Disposition
    reasons: tuple[str, ...]
    established_checks: tuple[str, ...]
    trust_context_digest: str


Checker = Callable[[Claim, CurrentTrust], CheckResult]


def _json(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def binding_for(claim: Claim, trust: CurrentTrust, check: str) -> str:
    """Deterministic anti-cross-context identifier, not a signed endorsement."""
    if check not in REQUIRED:
        raise ValueError("unknown evidence check")
    return hashlib.sha256(
        DOMAIN + b"check\x00" + _json({
            "check": check,
            "claim": {
                "operation_id": claim.operation_id,
                "action_digest": claim.action_digest,
                "target_audience": claim.target_audience,
                "policy_sha256": claim.policy_sha256,
                "policy_epoch": claim.policy_epoch,
                "actor_key_sha256": claim.actor_key_sha256,
                "issuer_key_sha256": claim.issuer_key_sha256,
                "effect_receipt_digest": claim.effect_receipt_digest,
                "issued_at": claim.issued_at,
                "expires_at": claim.expires_at,
            },
            "current_trust": trust.digest,
        })
    ).hexdigest()


def appraise(
    claim: Claim,
    trust: CurrentTrust,
    *,
    now: int,
    verifiers: Mapping[str, Checker],
) -> Appraisal:
    """Reappraise all obligations against CURRENT trusted verifier instances.

    Callbacks are the trust boundary: the caller must supply real trusted
    verifiers, not callbacks supplied by the agent or the issuing service.
    A callback exception or missing/untrusted result is UNDETERMINED.
    Explicit contradiction, expiry or trust-root mismatch is REJECTED.
    """
    if type(now) is not int or now < 0:
        raise ValueError("now must be a trusted nonnegative integer timestamp")
    structural = (
        ("action_digest", claim.action_digest, trust.action_digest),
        ("target_audience", claim.target_audience, trust.target_audience),
        ("policy_sha256", claim.policy_sha256, trust.policy_sha256),
        ("policy_epoch", claim.policy_epoch, trust.policy_epoch),
        ("actor_key_sha256", claim.actor_key_sha256, trust.actor_key_sha256),
        ("issuer_key_sha256", claim.issuer_key_sha256, trust.issuer_key_sha256),
    )
    reasons = [
        f"changed:{name}" for name, actual, current in structural if actual != current
    ]
    if now < claim.issued_at:
        reasons.append("not_yet_valid")
    if now >= claim.expires_at:
        reasons.append("expired")
    if reasons:
        return Appraisal(Disposition.REJECTED, tuple(reasons), (), trust.digest)

    specs = {s.check: s for s in trust.checkers}
    failures: list[str] = []
    unknowns: list[str] = []
    established: list[str] = []
    for check in REQUIRED:
        callback = verifiers.get(check)
        if callback is None:
            unknowns.append(f"missing_verifier:{check}")
            continue
        try:
            result = callback(claim, trust)
        except Exception:  # noqa: BLE001 - fail closed at external verifier boundary
            unknowns.append(f"verifier_error:{check}")
            continue
        if not isinstance(result, CheckResult):
            unknowns.append(f"invalid_verifier_result:{check}")
            continue
        expected = specs[check]
        if (
            result.verifier_id != expected.verifier_id
            or result.verifier_version != expected.version
            or result.claim_binding != binding_for(claim, trust, check)
        ):
            unknowns.append(f"stale_or_untrusted_result:{check}")
        elif result.outcome is Outcome.REFUTED:
            failures.append(f"refuted:{check}")
        elif result.outcome is Outcome.UNKNOWN:
            unknowns.append(f"not_established:{check}")
        else:
            established.append(check)

    if failures:
        return Appraisal(
            Disposition.REJECTED, tuple(failures + unknowns), tuple(established), trust.digest
        )
    if unknowns:
        return Appraisal(
            Disposition.UNDETERMINED, tuple(unknowns), tuple(established), trust.digest
        )
    return Appraisal(Disposition.ACCEPTED, (), tuple(established), trust.digest)
