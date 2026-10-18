"""Independent, source-agnostic tests for reliance transport under verifier change.

Test verifier callbacks are deliberately synthetic. They demonstrate the
reference contract's decision logic, not real signature, Cedar, execution
attestation or target-effect verification.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from pcs_bench.reliance_transport import (
    REQUIRED,
    Appraisal,
    CheckResult,
    Claim,
    CurrentTrust,
    Disposition,
    Outcome,
    VerifierSpec,
    appraise,
    binding_for,
)


def claim() -> Claim:
    return Claim(
        operation_id="effect-17",
        action_digest="a" * 64,
        target_audience="pcs-effect-target:lab-1",
        policy_sha256="b" * 64,
        policy_epoch=7,
        actor_key_sha256="c" * 64,
        issuer_key_sha256="d" * 64,
        effect_receipt_digest="e" * 64,
        issued_at=100,
        expires_at=160,
    )


def trust() -> CurrentTrust:
    evidence_sources = {
        "actor_signature": "actor-crypto",
        "issuer_signature": "issuer-crypto",
        "policy_result": "policy-replay",
        "issuer_execution": "execution-witness",
        "effect_observation": "effect-oracle",
    }
    c = claim()
    return CurrentTrust(
        action_digest=c.action_digest,
        target_audience=c.target_audience,
        policy_sha256=c.policy_sha256,
        policy_epoch=c.policy_epoch,
        actor_key_sha256=c.actor_key_sha256,
        issuer_key_sha256=c.issuer_key_sha256,
        observation_source="target-journal-v1",
        checkers=tuple(
            VerifierSpec(check=k, verifier_id=evidence_sources[k], version="1.0")
            for k in REQUIRED
        ),
    )


def all_checkers(
    context: CurrentTrust,
    *,
    outcomes: dict[str, Outcome] | None = None,
    replay_bindings: dict[str, str] | None = None,
):
    outcomes = outcomes or {}
    replay_bindings = replay_bindings or {}
    result = {}
    specs = {s.check: s for s in context.checkers}
    for name in REQUIRED:
        spec = specs[name]

        def verifier(c, current, name=name, spec=spec):
            return CheckResult(
                outcome=outcomes.get(name, Outcome.ESTABLISHED),
                verifier_id=spec.verifier_id,
                verifier_version=spec.version,
                claim_binding=replay_bindings.get(name, binding_for(c, current, name)),
            )

        result[name] = verifier
    return result


def check(
    c: Claim | None = None,
    t: CurrentTrust | None = None,
    *,
    verifiers=None,
) -> Appraisal:
    c = c or claim()
    t = t or trust()
    return appraise(c, t, now=120, verifiers=all_checkers(t) if verifiers is None else verifiers)


def test_five_distinct_trusted_checks_establish_reference_acceptance():
    result = check()
    assert result.disposition is Disposition.ACCEPTED
    assert result.established_checks == REQUIRED
    assert result.reasons == ()
    assert result.trust_context_digest == trust().digest


def test_signature_success_without_issuer_execution_is_indeterminate():
    t = trust()
    verifiers = all_checkers(t)
    verifiers.pop("issuer_execution")
    result = check(t=t, verifiers=verifiers)
    assert result.disposition is Disposition.UNDETERMINED
    assert "missing_verifier:issuer_execution" in result.reasons
    assert len(result.established_checks) == 4


def test_unknown_policy_replay_never_becomes_acceptance():
    t = trust()
    result = check(t=t, verifiers=all_checkers(t, outcomes={
        "policy_result": Outcome.UNKNOWN
    }))
    assert result.disposition is Disposition.UNDETERMINED
    assert result.reasons == ("not_established:policy_result",)


def test_unobserved_external_effect_is_unknown_even_when_every_signature_passes():
    t = trust()
    result = check(t=t, verifiers=all_checkers(t, outcomes={
        "effect_observation": Outcome.UNKNOWN
    }))
    assert result.disposition is Disposition.UNDETERMINED


@pytest.mark.parametrize("field,changed", [
    ("action_digest", "0" * 64),
    ("target_audience", "pcs-effect-target:lab-2"),
    ("policy_sha256", "f" * 64),
    ("policy_epoch", 8),
    ("actor_key_sha256", "0" * 64),
    ("issuer_key_sha256", "1" * 64),
])
def test_changed_reliance_assumption_invalidates_previous_approval(field, changed):
    t = replace(trust(), **{field: changed})
    result = check(t=t)
    assert result.disposition is Disposition.REJECTED
    assert result.reasons == (f"changed:{field}",)
    assert result.established_checks == ()


def test_rejected_claim_requires_no_callback_execution():
    t = replace(trust(), policy_epoch=9)

    def fail_if_called(*_args):
        raise AssertionError("stale reliance should not invoke any verifier")

    result = appraise(
        claim(), t, now=120, verifiers={x: fail_if_called for x in REQUIRED}
    )
    assert result.disposition is Disposition.REJECTED


def test_verified_signature_refutation_overrides_other_unknown_evidence():
    t = trust()
    verifiers = all_checkers(t, outcomes={"actor_signature": Outcome.REFUTED})
    verifiers.pop("issuer_execution")
    result = check(t=t, verifiers=verifiers)
    assert result.disposition is Disposition.REJECTED
    assert "refuted:actor_signature" in result.reasons
    assert "missing_verifier:issuer_execution" in result.reasons


def test_exact_verifier_version_change_requires_new_verification():
    t = trust()
    specs = tuple(
        replace(s, version="2.0") if s.check == "policy_result" else s
        for s in t.checkers
    )
    later = replace(t, checkers=specs)
    # The previously configured callbacks still report the OLD version.
    result = check(t=later, verifiers=all_checkers(t))
    assert result.disposition is Disposition.UNDETERMINED
    assert "stale_or_untrusted_result:policy_result" in result.reasons


def test_same_verifier_version_with_old_context_binding_cannot_be_reused():
    t = trust()
    c = claim()
    prev_binding = binding_for(c, t, "effect_observation")
    later = replace(t, observation_source="target-journal-v2")
    result = check(t=later, verifiers=all_checkers(later, replay_bindings={
        "effect_observation": prev_binding
    }))
    assert result.disposition is Disposition.UNDETERMINED
    assert "stale_or_untrusted_result:effect_observation" in result.reasons


def test_old_claim_evidence_cannot_be_reused_for_new_effect_receipt():
    t = trust()
    c = claim()
    previous_binding = binding_for(c, t, "effect_observation")
    changed = replace(c, effect_receipt_digest="f" * 64)
    result = check(c=changed, t=t, verifiers=all_checkers(t, replay_bindings={
        "effect_observation": previous_binding
    }))
    assert result.disposition is Disposition.UNDETERMINED


def test_callback_failure_is_explicitly_unknown_not_success():
    t = trust()
    verifiers = all_checkers(t)

    def unavailable(_claim, _trust):
        raise OSError("external witness unavailable")

    verifiers["effect_observation"] = unavailable
    result = check(t=t, verifiers=verifiers)
    assert result.disposition is Disposition.UNDETERMINED
    assert result.reasons == ("verifier_error:effect_observation",)


def test_callback_invalid_response_is_explicitly_unknown():
    t = trust()
    verifiers = all_checkers(t)
    verifiers["issuer_execution"] = lambda _c, _t: {"outcome": "established"}
    result = check(t=t, verifiers=verifiers)
    assert result.disposition is Disposition.UNDETERMINED
    assert result.reasons == ("invalid_verifier_result:issuer_execution",)


def test_current_verifier_reappraisal_is_not_cached_between_calls():
    t = trust()
    checks = all_checkers(t)
    first = check(t=t, verifiers=checks)
    assert first.disposition is Disposition.ACCEPTED
    checks["issuer_execution"] = lambda c, ctx: CheckResult(
        Outcome.UNKNOWN, "execution-witness", "1.0",
        binding_for(c, ctx, "issuer_execution")
    )
    assert check(t=t, verifiers=checks).disposition is Disposition.UNDETERMINED


def test_verifier_results_bound_to_exact_current_snapshot():
    t = trust()
    c = claim()
    old = binding_for(c, t, "actor_signature")
    changed = replace(t, checkers=tuple(reversed(t.checkers)))
    # Order of verifier declarations is not part of effective trust meaning.
    assert changed.digest == t.digest
    assert binding_for(c, changed, "actor_signature") == old
    assert binding_for(c, changed, "issuer_execution") != old


@pytest.mark.parametrize("now,reason", [
    (99, "not_yet_valid"),
    (160, "expired"),
    (161, "expired"),
])
def test_timestamp_boundaries_reject_old_and_future_claims(now, reason):
    result = appraise(claim(), trust(), now=now, verifiers={})
    assert result.disposition is Disposition.REJECTED
    assert result.reasons == (reason,)


def test_negative_or_boolean_timestamp_is_invalid_input():
    with pytest.raises(ValueError):
        appraise(claim(), trust(), now=-1, verifiers={})
    with pytest.raises(ValueError):
        appraise(claim(), trust(), now=True, verifiers={})


def test_context_must_have_all_five_independent_verifier_obligations():
    t = trust()
    with pytest.raises(ValueError, match="each assurance obligation"):
        replace(t, checkers=t.checkers[:-1])
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        replace(t, checkers=(*t.checkers, t.checkers[0]))
    duplicated_execution = tuple(
        replace(s, verifier_id="policy-replay") if s.check == "issuer_execution" else s
        for s in t.checkers
    )
    with pytest.raises(ValueError, match="must be distinct"):
        replace(t, checkers=duplicated_execution)


def test_hashes_are_checked_before_reliance_appraisal():
    with pytest.raises(ValueError, match="action_digest"):
        replace(claim(), action_digest="not-sha256")
    with pytest.raises(ValueError, match="issuer_key_sha256"):
        replace(trust(), issuer_key_sha256="fake")


def test_structurally_self_reported_success_cannot_replace_missing_checker():
    t = trust()
    # The input claim itself has no "signature_valid", "cedar_ran" or
    # "target_committed" flags. The trusted verifier MUST actually be called.
    assert check(t=t, verifiers={}).disposition is Disposition.UNDETERMINED


def test_no_policy_replay_is_treated_as_issuer_execution_evidence():
    t = trust()
    verifiers = all_checkers(t)
    verifiers.pop("issuer_execution")
    assert check(t=t, verifiers=verifiers).disposition is not Disposition.ACCEPTED


def test_actor_and_issuer_cannot_share_one_trust_root():
    t = trust()
    with pytest.raises(ValueError, match="must be distinct"):
        replace(t, issuer_key_sha256=t.actor_key_sha256)


def test_current_trust_digest_changes_with_source_and_verifier_epoch():
    original = trust()
    assert original.digest != replace(original, observation_source="target-journal-v2").digest
    assert original.digest != replace(original, policy_epoch=8).digest
    assert original.digest != replace(original, checkers=tuple(
        replace(spec, version="2.0") if spec.check == "issuer_execution" else spec
        for spec in original.checkers
    )).digest
