"""Real ACS policy and enforcing Agent Hooks, with a disposable effect target.

The actual Cedar decision comes from the upstream native ACS policy engine.
The host is cooperative: this does not establish complete mediation, trusted
policy distribution, or target-side authorization at commit time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.error import URLError

from pcs_bench.effect_boundary import Action, DispatchResult, action_digest, post_commit


@dataclass(frozen=True)
class AcsAuthorization:
    permitted: bool
    reason: str
    request_digest: str
    policy_epoch: int


class AcsEffectHost:
    """Trusted reference host for pinned, real Cedar-backed ACS."""

    def __init__(self, manifest: Path, *, epoch: int = 1) -> None:
        from agent_control_spec import AcsInterceptor
        from agent_hooks import EnforcementMode, InterceptionEmitter

        if epoch < 0:
            raise ValueError("epoch must be nonnegative")
        self._manifest = manifest.resolve(strict=True)
        self._manifest_sha256 = hashlib.sha256(self._manifest.read_bytes()).hexdigest()
        self._emitter = InterceptionEmitter(mode=EnforcementMode.ENFORCE)
        self._emitter.register(AcsInterceptor(str(self._manifest)), "acs-effect-policy")
        self._epoch = epoch
        self._revoked = False

    @property
    def epoch(self) -> int:
        return self._epoch

    @property
    def manifest_sha256(self) -> str:
        return self._manifest_sha256

    def change_policy_state(self, *, epoch: int, revoked: bool) -> None:
        """Simulate a new trusted policy-state snapshot for the host."""
        if epoch < self._epoch:
            raise ValueError("policy epoch must be monotonic")
        if not isinstance(revoked, bool):
            raise TypeError("revoked must be Boolean")
        self._epoch = epoch
        self._revoked = revoked

    async def _evaluate(self, action: Action, *, attempt: str) -> tuple[bool, str]:
        from agent_hooks import AgentContextBuilder, InterceptionBlocked

        # The trusted host, not the tool caller, supplies revocation state.
        args = {**action.to_dict(), "policy_revoked": self._revoked}
        builder = AgentContextBuilder(
            agent_id=action.principal,
            framework="pcs-bench-effect-study",
            session_id="isolated-acs-evaluation",
        )
        context = builder.pre_tool_call(
            call_id=f"{action.operation_id}:{attempt}",
            name="commit_disposable_effect",
            args=args,
        )
        try:
            outcome = await self._emitter.emit(context)
        except InterceptionBlocked as blocked:
            return False, str(blocked.result.verdict.reason or "blocked_by_acs")
        # A transformed request must be used by the host. This experiment
        # uses an allow/deny-only policy and rejects unexpected rewrites.
        if outcome.verdict.decision.value != "allow":
            return False, f"unsupported_verdict:{outcome.verdict.decision.value}"
        if outcome.target != args:
            return False, "unexpected_transformation"
        return True, "acs_allow"

    async def authorize(self, action: Action) -> AcsAuthorization:
        permitted, reason = await self._evaluate(action, attempt="authorization")
        return AcsAuthorization(permitted, reason, action_digest(action), self._epoch)

    async def dispatch(
        self,
        url: str,
        action: Action,
        authorization: AcsAuthorization,
        *,
        drop_reply_after_commit: bool = False,
    ) -> DispatchResult:
        if not authorization.permitted:
            return DispatchResult("blocked", "prior_acs_denial")
        if authorization.request_digest != action_digest(action):
            return DispatchResult("blocked", "action_mutated_after_acs")
        if authorization.policy_epoch != self._epoch:
            return DispatchResult("blocked", "policy_epoch_changed")
        permitted, reason = await self._evaluate(action, attempt="dispatch")
        if not permitted:
            return DispatchResult("blocked", f"dispatch_{reason}")
        try:
            code, receipt = post_commit(
                url, action, drop_reply_after_commit=drop_reply_after_commit
            )
        except (ConnectionError, OSError, TimeoutError, URLError) as exc:
            return DispatchResult("unknown", type(exc).__name__)
        if code == 200 and receipt.get("status") in ("committed", "deduplicated"):
            if receipt["status"] == "committed":
                return DispatchResult("committed", "target_receipt", receipt)
            return DispatchResult("deduplicated", "target_receipt", receipt)
        return DispatchResult("rejected", f"target_http_{code}", receipt)
