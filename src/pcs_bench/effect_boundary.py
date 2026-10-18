"""Experimental authorization-to-effect contract for a disposable target.

This module authenticates neither the caller nor the policy authority. The
caller supplies a trusted, immutable policy snapshot for each local test.
Target effects are observed separately through a target-owned SQLite journal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Action:
    operation_id: str
    principal: str
    tenant: str
    resource: str
    delta: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "operation_id": self.operation_id,
            "principal": self.principal,
            "tenant": self.tenant,
            "resource": self.resource,
            "delta": self.delta,
        }


@dataclass(frozen=True)
class Policy:
    principal: str
    tenant: str
    resources: tuple[str, ...]
    max_abs_delta: int
    epoch: int
    revoked: bool = False


@dataclass(frozen=True)
class Decision:
    permitted: bool
    reason: str
    request_digest: str
    policy_epoch: int


@dataclass(frozen=True)
class DispatchResult:
    status: Literal["blocked", "committed", "deduplicated", "unknown", "rejected"]
    reason: str
    target_receipt: dict[str, object] | None = None


def _canonical(data: dict[str, str | int]) -> bytes:
    """Research-only canonical bytes; not RFC 8785 or a signed record."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def action_digest(action: Action) -> str:
    return hashlib.sha256(b"agent-effect-study-action-v1\0" + _canonical(action.to_dict())).hexdigest()


def decide(action: Action, policy: Policy) -> Decision:
    """Evaluate one action under a caller-supplied pinned policy snapshot."""
    reason = "permit"
    if not action.operation_id or not action.principal or not action.tenant or not action.resource:
        reason = "invalid_action"
    elif not isinstance(action.delta, int) or isinstance(action.delta, bool):
        reason = "invalid_delta"
    elif not isinstance(policy.epoch, int) or policy.epoch < 0:
        reason = "invalid_policy_epoch"
    elif policy.revoked:
        reason = "revoked"
    elif action.principal != policy.principal or action.tenant != policy.tenant:
        reason = "principal_or_tenant_mismatch"
    elif action.resource not in policy.resources:
        reason = "resource_not_granted"
    elif abs(action.delta) > policy.max_abs_delta:
        reason = "amount_exceeds_grant"
    return Decision(reason == "permit", reason, action_digest(action), policy.epoch)


def dispatch(
    url: str,
    action: Action,
    decision: Decision,
    current_policy: Policy,
    *,
    drop_reply_after_commit: bool = False,
) -> DispatchResult:
    """Rebind a decision at dispatch, then request a disposable target commit.

    This mediator is cooperative: direct target access bypasses it. Validation
    cannot establish complete mediation or the authenticity of policy objects.
    """
    if not decision.permitted:
        return DispatchResult("blocked", "prior_denial")
    if decision.request_digest != action_digest(action):
        return DispatchResult("blocked", "action_changed_after_approval")
    if decision.policy_epoch != current_policy.epoch:
        return DispatchResult("blocked", "policy_epoch_changed")
    current = decide(action, current_policy)
    if not current.permitted:
        return DispatchResult("blocked", f"dispatch_{current.reason}")
    try:
        status_code, receipt = post_commit(
            url, action, drop_reply_after_commit=drop_reply_after_commit
        )
    except (ConnectionError, OSError, TimeoutError, URLError) as exc:
        return DispatchResult("unknown", type(exc).__name__)
    if status_code == 200 and receipt.get("status") == "committed":
        return DispatchResult("committed", "target_confirmed", receipt)
    if status_code == 200 and receipt.get("status") == "deduplicated":
        return DispatchResult("deduplicated", "target_confirmed_existing", receipt)
    return DispatchResult("rejected", f"target_status_{status_code}", receipt)


def post_commit(
    url: str,
    action: Action,
    *,
    drop_reply_after_commit: bool = False,
) -> tuple[int, dict[str, object]]:
    """Send exactly one target request, with no implicit retries."""
    payload: dict[str, object] = action.to_dict()
    payload["drop_reply_after_commit"] = drop_reply_after_commit
    request = Request(
        url.rstrip("/") + "/commit",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read(32768))
    except HTTPError as err:
        try:
            body = json.loads(err.read(32768))
        except (ValueError, UnicodeError):
            body = {"error": "unparseable_target_response"}
        return err.code, body


def read_target(url: str, route: Literal["journal", "state"]) -> dict[str, object]:
    """Read the disposable service's own storage view, independently of broker logs."""
    with urlopen(url.rstrip("/") + "/" + route, timeout=3) as response:
        return json.loads(response.read(131072))
