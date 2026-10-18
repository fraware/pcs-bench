"""Positive/negative controls for authorization and request binding."""

from dataclasses import replace

from pcs_bench.effect_boundary import Action, Policy, action_digest, decide, dispatch


def action(**changes: object) -> Action:
    return replace(Action("op-1", "agent-1", "tenant-a", "account:a", 5), **changes)


def policy(**changes: object) -> Policy:
    return replace(Policy("agent-1", "tenant-a", ("account:a",), 10, 3), **changes)


def test_same_action_has_stable_digest():
    assert action_digest(action()) == action_digest(action())


def test_different_payload_changes_digest():
    for modified in (
        action(operation_id="op-2"), action(delta=6), action(resource="account:b"),
        action(principal="other"), action(tenant="other"),
    ):
        assert action_digest(modified) != action_digest(action())


def test_permits_granted_action():
    result = decide(action(), policy())
    assert (result.permitted, result.reason, result.policy_epoch) == (True, "permit", 3)
    assert result.request_digest == action_digest(action())


def test_denies_unauthorized_principal_and_tenant():
    for item in (action(principal="other"), action(tenant="other")):
        assert decide(item, policy()).reason == "principal_or_tenant_mismatch"


def test_denies_unlisted_resource_and_excessive_delta():
    assert decide(action(resource="account:b"), policy()).reason == "resource_not_granted"
    assert decide(action(delta=11), policy()).reason == "amount_exceeds_grant"
    assert decide(action(delta=-11), policy()).reason == "amount_exceeds_grant"


def test_denies_revoked_policy():
    assert decide(action(), policy(revoked=True)).reason == "revoked"


def test_denies_boolean_delta_and_invalid_epoch():
    assert decide(action(delta=True), policy()).reason == "invalid_delta"
    assert decide(action(), policy(epoch=-1)).reason == "invalid_policy_epoch"


def test_dispatch_denied_without_target_connection():
    denied = decide(action(delta=20), policy())
    result = dispatch("http://127.0.0.1:1", action(delta=20), denied, policy())
    assert (result.status, result.reason) == ("blocked", "prior_denial")


def test_dispatch_detects_mutation_before_external_contact():
    decided = decide(action(), policy())
    result = dispatch("http://127.0.0.1:1", action(delta=7), decided, policy())
    assert (result.status, result.reason) == ("blocked", "action_changed_after_approval")


def test_dispatch_detects_policy_epoch_change_before_external_contact():
    decided = decide(action(), policy())
    result = dispatch("http://127.0.0.1:1", action(), decided, policy(epoch=4))
    assert (result.status, result.reason) == ("blocked", "policy_epoch_changed")


def test_dispatch_detects_same_epoch_revocation_before_external_contact():
    decided = decide(action(), policy())
    result = dispatch("http://127.0.0.1:1", action(), decided, policy(revoked=True))
    assert (result.status, result.reason) == ("blocked", "dispatch_revoked")
