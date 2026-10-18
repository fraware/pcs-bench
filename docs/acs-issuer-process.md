# Restricted ACS issuer process and externally replayed decisions

**Status:** isolated local research issuer, not a production policy decision
point, a confidential computing implementation, or independently verified
evidence that a given ACS evaluation happened.

## Why this is the next boundary

Earlier, the example host held both an actor client key and a policy-issuer
key. It could call `sign_decision` directly without evaluating the intended
Cedar policy. The resulting authorization was authentic as a signature but
the **policy-evaluation claim depended entirely on issuer honesty**.

`src/pcs_bench/acs_issuer_service.py` now executes the actual ACS/Cedar
policy in **its own loopback-only operating-system process**. The actor/test
client never receives that process's ephemeral issuer private key.

There is a single data-plane HTTP signing interface:

`POST /authorize` with **exactly** `{"action": ..., "actor_key_id": ...}`.

The service validates the action and pinned actor key, runs the real ACS
`pre_tool_call` policy under `EnforcementMode.ENFORCE`, and returns a
separately signed target-bound `allow` **only if** the real evaluation
permits the request. A Cedar denial returns an explicit refusal, with no
authorization token. The public key is exported to the trusted local
operator for enrollment into the independent target's issuer registry.
There is no `/sign`, `/issue-unchecked`, `/set-policy`, `/set-key`, or
remote key-enrollment API.

Both the manifest and Cedar file bytes are SHA-256 pinned at start. They
are checked before each evaluation. If either changes, the issuer fails
closed. The issuer ID, target audience, signing key and policy epoch are
configured by the local operator, **not** by authorization callers.

The separate target process in `dual_authority_target.py` still requires
both the actor's valid signed request and the issuer's independently signed
policy decision **inside the same SQLite commit transaction**. Client and
issuer cannot overwrite the target's current policy or revocation data
through HTTP.

## Positive and adversarial controls

`tests/integration/test_acs_issuer_service.py` exercises two independent
subprocesses (issuer and target), with an actor private key held only by
the test client. It tests:

1. A permitted Cedar request produces a signed permission whose action
   digest matches the requested operation. The separate target commits
   one effect, and an independent *second execution of the same ACS
   implementation* agrees with the allow decision.
2. A Cedar-denied excessive amount produces **no signed permission** and
   no target effect.
3. A caller cannot inject an `allow` verdict, choose an alternative policy
   digest, request issuance for a different actor key or access a raw-sign
   endpoint.
4. A change in pinned Cedar file bytes after issuer startup prevents
   further token issuance.
5. Target-side revocation after issuance invalidates the stale token at
   commit.
6. Altering the action after token issuance is rejected by the target's
   cryptographic action binding.

The issuer's `GET /audit` endpoint provides source-checkable diagnostic
records of policy requests, outcomes, ACS reason strings, policy hashes,
and issued decision IDs. These records are **not** independently witnessed,
signed, or omission-detectable; their existence does not establish the
absence of other events.

## How to reproduce

```bash
python -m pip install -e ".[dev]" \
  "agent-control-spec==0.4.0a4" "cryptography==46.0.4" ruff
ACS_EFFECT_INTEGRATION=1 python -m pytest -q \
  tests/integration/test_acs_issuer_service.py
```

The dedicated GitHub Actions workflow includes these tests and strict lint
under Python 3.11 and 3.12. Published ACS `0.4.0a4` still requires the
explicit documented principal-snapshot compatibility projection used by
the rest of this experimental suite. This is not a claim that a later
beta release has been verified.

## Assurance boundaries and critical remaining work

**Process separation is not hardware separation or cryptographic proof of
software execution.** A compromised issuer process, malicious local
administrator, attacker controlling the same host/OS, or replacement of
the issuer executable could still produce false signed permissions.
An issuer-authored audit record is self-reported evidence, and replaying
the decision with the same policy SDK is only a consistency test, not an
independent proof of the implementation's correctness.

A real relying party would still need organizational policy-authority
governance, authenticated workload identity, protected key custody,
measured or independently monitored issuer deployment, secure transport,
secure time, and independently witnessed evidence.

The next high-value research task is to add a **separately appraised
evidence-transport contract**: source-policy digest, evaluation-input
commitment, verifier identity/version, issuer attestation if available,
and a relying-party acceptance predicate. We must distinguish a signed
assertion of evaluation from independent evidence that it happened.

All changes stay on an open research branch. The main repository's
unrelated CI failure and an independent review remain merge blockers.
