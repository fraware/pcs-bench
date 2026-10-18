"""Human-labeled temporal transport fixtures and adversarial model invariants.

Fixture labels were authored separately from the evaluator. They are
provisional normative hypotheses, NOT independent external ground truth.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pcs_bench.temporal_reliance import (
    DEPENDENCIES,
    Case,
    Change,
    ChangeMode,
    Dependency,
    Proposition,
    Transport,
    evaluate,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/temporal_transport/v1/cases.json"
)


def load_cases() -> list[dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema"] == "pcs-temporal-reliance-fixtures-v1"
    return payload["cases"]


def parse_case(record: dict) -> Case:
    c = record["change"]
    return Case(
        case_id=record["id"],
        proposition=Proposition(record["proposition"]),
        event_at=record["event_at"],
        appraisal_at=record["appraisal_at"],
        change=Change(
            dependency=Dependency(c["dependency"]),
            mode=ChangeMode(c["mode"]),
            effective_at=c["effective_at"],
            verified_bridge=c.get("verified_bridge", False),
            verified_refutation=c.get("verified_refutation", False),
        ),
    )


@pytest.mark.parametrize("entry", load_cases(), ids=lambda c: c["id"])
def test_hand_labeled_reference_cases(entry: dict):
    case = parse_case(entry)
    outcome = evaluate(case)
    assert outcome.transport == Transport(entry["expected"]), (
        case.case_id, entry["rationale"], outcome
    )
    assert entry["rationale"]
    assert outcome.reason


def test_cases_are_unique_and_cover_all_proposition_kinds_and_outputs():
    cases = load_cases()
    assert len(cases) >= 30
    assert len({c["id"] for c in cases}) == len(cases)
    assert {x["proposition"] for x in cases} == {x.value for x in Proposition}
    assert {x["expected"] for x in cases} == {x.value for x in Transport}
    assert {x["change"]["dependency"] for x in cases} == {
        "policy", "actor_key", "issuer_key", "verifier",
        "effect_observation", "execution_witness", "target", "action_input",
    }


def test_historical_occurrence_is_distinct_from_current_authorization():
    base = parse_case(load_cases()[0])
    historical = evaluate(base)
    current = evaluate(replace(base, proposition=Proposition.CURRENT_AUTHORIZATION))
    assert historical.transport is Transport.PRESERVE
    assert current.transport is Transport.REAPPRAISE


def test_post_event_revocation_does_not_erase_historical_authorization():
    base = Case(
        "historical-test",
        Proposition.HISTORICAL_AUTHORIZATION,
        100,
        150,
        Change(Dependency.ACTOR_KEY, ChangeMode.REVOKED, 130),
    )
    assert evaluate(base).transport is Transport.PRESERVE
    assert evaluate(replace(
        base, change=replace(base.change, effective_at=90)
    )).transport is Transport.REAPPRAISE


def test_confirmed_pre_event_refutation_is_not_merely_missing_evidence():
    c = Case(
        "refutation",
        Proposition.HISTORICAL_AUTHORIZATION,
        100, 150,
        Change(Dependency.ISSUER_KEY, ChangeMode.CONTRADICTED, 90,
               verified_refutation=True),
    )
    assert evaluate(c).transport is Transport.WITHDRAW
    unknown = replace(c, change=Change(
        Dependency.ISSUER_KEY, ChangeMode.UNAVAILABLE, 90
    ))
    assert evaluate(unknown).transport is Transport.REAPPRAISE


def test_unrelated_changes_preserve_prior_reliance():
    for p in Proposition:
        for d in Dependency:
            if d not in DEPENDENCIES[p]:
                c = Case("unrelated", p, 100, 150, Change(d, ChangeMode.UPDATED, 110))
                assert evaluate(c).transport is Transport.PRESERVE


def test_verified_bridge_and_refutation_do_not_coexist():
    with pytest.raises(ValueError, match="simultaneously"):
        Change(Dependency.POLICY, ChangeMode.UPDATED, 100, True, True)
    with pytest.raises(ValueError, match="explicit contradiction"):
        Change(Dependency.POLICY, ChangeMode.CONTRADICTED, 100, True, False)


def test_untrusted_timestamps_cannot_use_boolean_values():
    with pytest.raises(ValueError, match="effective time"):
        Change(Dependency.POLICY, ChangeMode.UPDATED, True)
    with pytest.raises(ValueError, match="timestamps"):
        Case("x", Proposition.CURRENT_AUTHORIZATION, True, 100,
             Change(Dependency.POLICY, ChangeMode.UPDATED, 90))
    with pytest.raises(ValueError, match="timestamps"):
        Case("x", Proposition.CURRENT_AUTHORIZATION, 50, False,
             Change(Dependency.POLICY, ChangeMode.UPDATED, 20))


def test_evaluation_rejects_event_in_the_future():
    with pytest.raises(ValueError, match="after appraisal"):
        Case("x", Proposition.HISTORICAL_AUTHORIZATION, 150, 100,
             Change(Dependency.POLICY, ChangeMode.UPDATED, 90))


def test_future_effective_change_does_not_withdraw_current_authority():
    future = Case(
        "future", Proposition.CURRENT_AUTHORIZATION, 100, 150,
        Change(Dependency.ACTOR_KEY, ChangeMode.REVOKED, 170,
               verified_refutation=True),
    )
    assert evaluate(future).transport is Transport.PRESERVE


def test_verified_refutation_only_affects_dependent_proposition():
    c = Case(
        "negative", Proposition.HISTORICAL_OCCURRENCE, 100, 150,
        Change(Dependency.ACTOR_KEY, ChangeMode.CONTRADICTED, 90,
               verified_refutation=True),
    )
    assert evaluate(c).transport is Transport.PRESERVE
    altered = replace(c, change=replace(
        c.change, dependency=Dependency.EFFECT_OBSERVATION
    ))
    assert evaluate(altered).transport is Transport.WITHDRAW


def test_no_result_proves_underlying_historical_truth():
    # The reference output is a REUSE decision, not an object containing an
    # assertion of the event, external signature verification, or target state.
    c = parse_case(load_cases()[0])
    result = evaluate(c)
    assert set(result.__dataclass_fields__) == {"transport", "reason"}
    assert result.transport is Transport.PRESERVE
