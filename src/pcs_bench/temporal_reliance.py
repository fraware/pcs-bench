"""Minimal temporal reliance reference model for human-labeled research cases.

This module evaluates whether one prior positive appraisal can still be
relied on after one explicitly described contextual change. It does not
verify evidence, prove a historical proposition, check live revocation
registries, or authorize a real external effect.

The two verification flags are TRUSTED oracle assumptions. Untrusted agent
input must never be allowed to set them in a security-sensitive application.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Proposition(str, Enum):
    HISTORICAL_OCCURRENCE = "historical_occurrence"
    HISTORICAL_AUTHORIZATION = "historical_authorization"
    POLICY_DECISION_CORRECTNESS = "policy_decision_correctness"
    ISSUER_EXECUTION = "issuer_execution"
    CURRENT_AUTHORIZATION = "current_authorization"


class Dependency(str, Enum):
    POLICY = "policy"
    ACTOR_KEY = "actor_key"
    ISSUER_KEY = "issuer_key"
    VERIFIER = "verifier"
    EFFECT_OBSERVATION = "effect_observation"
    EXECUTION_WITNESS = "execution_witness"
    TARGET = "target"
    ACTION_INPUT = "action_input"


class ChangeMode(str, Enum):
    UPDATED = "updated"
    REVOKED = "revoked"
    UNAVAILABLE = "unavailable"
    CONTRADICTED = "contradicted"


class Transport(str, Enum):
    PRESERVE = "preserve"
    REAPPRAISE = "reappraise"
    WITHDRAW = "withdraw"


DEPENDENCIES: dict[Proposition, frozenset[Dependency]] = {
    Proposition.HISTORICAL_OCCURRENCE: frozenset({
        Dependency.EFFECT_OBSERVATION, Dependency.VERIFIER, Dependency.TARGET,
        Dependency.ACTION_INPUT,
    }),
    Proposition.HISTORICAL_AUTHORIZATION: frozenset({
        Dependency.POLICY, Dependency.ACTOR_KEY, Dependency.ISSUER_KEY,
        Dependency.EXECUTION_WITNESS, Dependency.VERIFIER,
        Dependency.TARGET, Dependency.ACTION_INPUT,
    }),
    Proposition.POLICY_DECISION_CORRECTNESS: frozenset({
        Dependency.POLICY, Dependency.VERIFIER, Dependency.ACTION_INPUT,
    }),
    Proposition.ISSUER_EXECUTION: frozenset({
        Dependency.EXECUTION_WITNESS, Dependency.VERIFIER,
        Dependency.ACTION_INPUT,
    }),
    Proposition.CURRENT_AUTHORIZATION: frozenset({
        Dependency.POLICY, Dependency.ACTOR_KEY, Dependency.ISSUER_KEY,
        Dependency.EXECUTION_WITNESS, Dependency.VERIFIER,
        Dependency.TARGET, Dependency.ACTION_INPUT,
    }),
}

# Changes to live authority after an event are not automatically changes
# to the authority that was applicable at the time of that event.
TEMPORAL_AUTHORITY = frozenset({
    Dependency.POLICY, Dependency.ACTOR_KEY, Dependency.ISSUER_KEY,
})


@dataclass(frozen=True, slots=True)
class Change:
    dependency: Dependency
    mode: ChangeMode
    effective_at: int
    verified_bridge: bool = False
    verified_refutation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.dependency, Dependency):
            raise ValueError("invalid dependency")
        if not isinstance(self.mode, ChangeMode):
            raise ValueError("invalid change mode")
        if type(self.effective_at) is not int or self.effective_at < 0:
            raise ValueError("invalid effective time")
        if type(self.verified_bridge) is not bool or type(self.verified_refutation) is not bool:
            raise ValueError("verification flags must be Boolean")
        if self.verified_bridge and self.verified_refutation:
            raise ValueError("a bridge cannot simultaneously refute its proposition")
        if self.verified_bridge and self.mode in {
            ChangeMode.CONTRADICTED, ChangeMode.REVOKED
        }:
            raise ValueError("cannot bridge a contradiction or revocation")
        if self.verified_refutation and self.mode not in {
            ChangeMode.CONTRADICTED, ChangeMode.REVOKED
        }:
            raise ValueError("refutation requires contradiction or revocation")


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    proposition: Proposition
    event_at: int
    appraisal_at: int
    change: Change

    def __post_init__(self) -> None:
        if not self.case_id or not self.case_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid case identifier")
        if not isinstance(self.proposition, Proposition):
            raise ValueError("invalid proposition")
        if type(self.event_at) is not int or type(self.appraisal_at) is not int:
            raise ValueError("timestamps must be integers")
        if self.event_at < 0 or self.event_at > self.appraisal_at:
            raise ValueError("event cannot occur after appraisal")


@dataclass(frozen=True, slots=True)
class Decision:
    transport: Transport
    reason: str


def evaluate(case: Case) -> Decision:
    """Decide reuse of a PRIOR ESTABLISHED result, never historical truth.

    WITHDRAW means withdraw prior positive reliance, not assert that an
    earlier recorded event did not happen. Verified refutations are trusted
    evaluator-provided evidence, not inferred from unsigned input.
    """
    change = case.change
    if change.effective_at > case.appraisal_at:
        return Decision(Transport.PRESERVE, "not_yet_effective")

    if change.dependency not in DEPENDENCIES[case.proposition]:
        return Decision(Transport.PRESERVE, "irrelevant_dependency")

    if (
        case.proposition in {
            Proposition.HISTORICAL_AUTHORIZATION,
            Proposition.POLICY_DECISION_CORRECTNESS,
        }
        and change.dependency in TEMPORAL_AUTHORITY
        and change.effective_at > case.event_at
    ):
        return Decision(Transport.PRESERVE, "post_event_authority_change")

    if change.verified_refutation:
        return Decision(Transport.WITHDRAW, "independently_refuted")

    if change.verified_bridge:
        return Decision(Transport.PRESERVE, "independently_verified_bridge")

    return Decision(Transport.REAPPRAISE, "affected_dependency_requires_reappraisal")
