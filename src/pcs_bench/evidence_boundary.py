"""Independent, three-valued checks at the agent evidence boundary.

This module compares *claims* to caller-supplied independent facts. It does not
authenticate those facts, verify cryptographic signatures, check Lean proofs, or
observe actual effects. Treat "consistent" as conditional on the caller's
independent evidence and trust root, never as a release authorization.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

Status = Literal["consistent", "contradicted", "insufficient"]


@dataclass(frozen=True)
class BoundaryCheck:
    status: Status
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class BoundaryReport:
    authority: BoundaryCheck
    scope: BoundaryCheck
    footprint: BoundaryCheck
    proof: BoundaryCheck

    @property
    def status(self) -> Status:
        statuses = (
            self.authority.status,
            self.scope.status,
            self.footprint.status,
            self.proof.status,
        )
        if "contradicted" in statuses:
            return "contradicted"
        if "insufficient" in statuses:
            return "insufficient"
        return "consistent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authority": self.authority.to_dict(),
            "scope": self.scope.to_dict(),
            "footprint": self.footprint.to_dict(),
            "proof": self.proof.to_dict(),
            "assurance_limit": (
                "Only consistency with supplied external evidence is checked; "
                "source authenticity, completeness, effect commitment, and Lean proof "
                "verification are not established by this report."
            ),
        }


def _check(status: Status, code: str, detail: str) -> BoundaryCheck:
    return BoundaryCheck(status=status, code=code, detail=detail)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _action(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(observation.get("action"))


def _principal(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    action = _action(observation)
    return _mapping(action.get("principal") or observation.get("principal"))


def _resources(action: Mapping[str, Any], key: str) -> list[Mapping[str, Any]] | None:
    raw = action.get(key)
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        return None
    return raw


def _glob_match_only_star(pattern: str, uri: str) -> bool:
    """Lexical '*' glob only; deliberately avoids fnmatch '?' and '[]' semantics."""
    expression = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(expression, uri, flags=re.DOTALL) is not None


def authority_consistency(
    observation: Mapping[str, Any],
    grant: Mapping[str, Any] | None,
) -> BoundaryCheck:
    """Compare to independently supplied grant facts; do not authenticate a grant."""
    if grant is None:
        return _check("insufficient", "AUTHORITY_NOT_SUPPLIED", "No external grant supplied")
    principal = _principal(observation)
    capability = _mapping(_action(observation).get("capability"))
    actor = principal.get("id")
    tenant = principal.get("tenant_id")
    cap = capability.get("id")
    granted = grant.get("effective_capabilities")
    if not (isinstance(actor, str) and isinstance(tenant, str) and isinstance(cap, str)):
        return _check("insufficient", "ACTION_IDENTITY_INCOMPLETE", "No complete action identity")
    if not isinstance(granted, list) or any(not isinstance(x, str) for x in granted):
        return _check(
            "insufficient",
            "GRANT_CAPABILITIES_UNKNOWN",
            "External grant omits a valid capability inventory",
        )
    if actor != grant.get("principal_id") or tenant != grant.get("tenant_id"):
        return _check("contradicted", "GRANT_SUBJECT_MISMATCH", "Source and grant subjects differ")
    if cap not in granted:
        return _check("contradicted", "CAPABILITY_NOT_GRANTED", "Claimed capability absent in grant")
    return _check(
        "consistent",
        "GRANT_MATCHES_REQUEST",
        "Capability and subject match supplied grant (grant authenticity unverified)",
    )


def scope_consistency(
    observation: Mapping[str, Any],
    trusted_catalog: Mapping[str, str] | None,
) -> BoundaryCheck:
    """Compare with a separately supplied capability catalog before matching URIs."""
    action = _action(observation)
    capability = _mapping(action.get("capability"))
    pattern = capability.get("resource_pattern")
    cap_id = capability.get("id")
    if not isinstance(pattern, str) or not pattern or not isinstance(cap_id, str):
        return _check("insufficient", "SCOPE_UNSPECIFIED", "No complete capability scope")
    if trusted_catalog is None:
        return _check("insufficient", "CAPABILITY_CATALOG_ABSENT", "No independent catalog")
    trusted_pattern = trusted_catalog.get(cap_id)
    if not isinstance(trusted_pattern, str) or not trusted_pattern:
        return _check("insufficient", "CAPABILITY_UNKNOWN", "Capability absent from catalog")
    if pattern != trusted_pattern:
        return _check(
            "contradicted",
            "CAPABILITY_SCOPE_MISMATCH",
            "Observed capability pattern disagrees with independent catalog",
        )
    reads, writes = _resources(action, "reads"), _resources(action, "writes")
    if reads is None or writes is None or not (reads or writes):
        return _check("insufficient", "SCOPE_FOOTPRINT_MISSING", "Resource list absent or empty")
    for resource in reads + writes:
        uri = resource.get("uri")
        if not isinstance(uri, str) or not uri:
            return _check("insufficient", "RESOURCE_URI_MISSING", "Resource URI unavailable")
        if not _glob_match_only_star(pattern, uri):
            return _check(
                "contradicted", "RESOURCE_OUTSIDE_SCOPE", f"{uri!r} does not match {pattern!r}"
            )
    return _check(
        "consistent", "RESOURCES_IN_DECLARED_SCOPE", "All declared resource URIs match"
    )


def footprint_consistency(
    observation: Mapping[str, Any],
    independent_footprint: Mapping[str, Any] | None,
) -> BoundaryCheck:
    """Compare *declared* read/write URIs to separately observed read/write URIs."""
    if independent_footprint is None:
        return _check("insufficient", "EFFECT_ORACLE_ABSENT", "No independent footprint supplied")
    action = _action(observation)
    for key in ("reads", "writes"):
        recorded = _resources(action, key)
        expected = independent_footprint.get(key)
        if recorded is None or not isinstance(expected, list) or any(
            not isinstance(uri, str) for uri in expected
        ):
            return _check(
                "insufficient", "EFFECT_FOOTPRINT_INCOMPLETE", f"Invalid {key} inventory"
            )
        recorded_uris = [entry.get("uri") for entry in recorded]
        if any(not isinstance(uri, str) or not uri for uri in recorded_uris):
            return _check(
                "insufficient", "EFFECT_RESOURCE_UNRESOLVED", f"Unresolved {key} resource"
            )
        if sorted(recorded_uris) != sorted(expected):
            return _check(
                "contradicted",
                "EFFECT_FOOTPRINT_MISMATCH",
                f"Recorded {key} does not equal independently supplied {key}",
            )
    return _check(
        "consistent",
        "DECLARED_FOOTPRINT_MATCHES",
        "Declared accesses agree with independent inventory (oracle authenticity unverified)",
    )


def proof_claim_consistency(
    certificate: Mapping[str, Any] | None,
    *,
    required_class: str = "LeanKernelChecked",
) -> BoundaryCheck:
    """Prevent structural promotion of legacy claims; never perform proof verification."""
    if certificate is None:
        return _check("insufficient", "CERTIFICATE_ABSENT", "No certificate supplied")
    claim_class = certificate.get("claim_class")
    if claim_class != required_class:
        return _check(
            "contradicted",
            "PROOF_CLASS_MISMATCH",
            f"Claim {claim_class!r} cannot satisfy required {required_class!r}",
        )
    return _check(
        "insufficient",
        "INDEPENDENT_PROOF_CHECK_REQUIRED",
        "Claim label matches, but concrete Lean proof and artifact bindings must be verified",
    )


def assess_evidence_boundary(
    observation: Mapping[str, Any],
    *,
    independent_grant: Mapping[str, Any] | None = None,
    independent_footprint: Mapping[str, Any] | None = None,
    trusted_catalog: Mapping[str, str] | None = None,
    certificate: Mapping[str, Any] | None = None,
) -> BoundaryReport:
    """Produce a diagnostic report. Never treat it as an authorization or attestation."""
    return BoundaryReport(
        authority=authority_consistency(observation, independent_grant),
        scope=scope_consistency(observation, trusted_catalog),
        footprint=footprint_consistency(observation, independent_footprint),
        proof=proof_claim_consistency(certificate),
    )
