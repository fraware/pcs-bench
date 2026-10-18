# Target-enforced agent effects: deterministic revocation and commit-time appraisal

**Status: experimental research**, implemented on the `pcs-bench` research branch. This is not a production policy enforcement point, an authenticated identity system, a formal model of SQLite, or a claim of end-to-end runtime safety.

## Research question

An agent obtains permission, stages an operation, and then the governing policy changes before the external system durably applies that operation. Does the *effecting target* use the current policy, or does it blindly trust the earlier host decision?

The previous study used a cooperative host and an intentionally open effect target. This extension adds a **different** disposable target with an independently provisioned local SQLite authority table, no HTTP administrator endpoint, and authorization checked in the **same `BEGIN IMMEDIATE` transaction** that writes effects and balances.

It distinguishes:
- A correct host ACS/Cedar verdict.
- A staged action with an exact request digest and a recorded policy epoch.
- The target's current policy at commit.
- Actual committed effects in the target-owned journal.
- Policy updates ordered against commits by SQLite transaction locking.

The target does **not** know whether the HTTP caller is really `agent-1`: principal and tenant values are still self-asserted strings. An attacker able to submit those values can carry out an otherwise-permitted direct request. A regression case deliberately demonstrates this remaining gap.

## Target protocol and invariants

Files: `src/pcs_bench/guarded_target.py` and `src/pcs_bench/guarded_study.py`.

`POST /stage` accepts a strictly typed action and records its SHA-256 request commitment, fields and current policy epoch. **No balance change happens at this step.**

`POST /commit-staged` accepts only `operation_id` and `request_digest`, retrieves the stored immutable action, compares digests and then checks the **current target-owned policy and original stage epoch inside the same database write transaction as the effect**. Revocation or scope contraction rejects the commit. A monotonic policy-version change also invalidates an old stage even if the new policy still allows the action.

`POST /commit` attempts a direct one-step effect, also subject to target-owned policy checks in its SQLite transaction. This allows us to test actual target enforcement when the cooperative ACS host is bypassed.

The only authority mutation operation, `operator_update(database, next_epoch=..., revoked=...)`, is invoked by trusted local test code with direct database access. There is no HTTP API for modifying it. Updates require a strictly increasing epoch and serialize with effect commits. This is a controlled trusted-operator fixture, **not cryptographically authenticated policy distribution**.

Idempotency keys are bound to action digests and are unique. A committed identical request can be read back as `deduplicated` after revocation without creating a new effect. A different payload with the same operation ID is rejected.

### Precisely bounded property

For any **new committed** effect recorded by this SQLite target, the same write transaction checked that the locally provisioned authority was unrevoked, matched the asserted principal/tenant/resource, permitted the amount, and, for a staged operation, had the same epoch as when it was staged.

This is a model- and implementation-relative claim supported by direct tests; it is **not** a machine-checked mathematical proof, a guarantee about a malicious local database administrator, or proof of trusted actor identity.

## Reproduction

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/integration/test_guarded_effect_target.py

python -m pip install "agent-control-spec==0.4.0a4"
ACS_EFFECT_INTEGRATION=1 python -m pytest -q \
  tests/integration/test_acs_guarded_target.py
python -m pcs_bench.guarded_study --out reports/acs-guarded-target-study.json
```

The dedicated GitHub Actions workflow runs both Python 3.11 and 3.12, uses the actual published ACS native/Cedar package and Agent Hooks in enforcing mode, runs strict Ruff checks, and archives the JSON reports.

## Negative and positive controls

The target-only suite contains **14 tests**, including an allowed staged commit, staged revocation before commit, grant contraction, epoch changes without revocation, tampered stage receipts, a forbidden direct call, a deliberately forged identity claim, post-revocation idempotent replay, 20 concurrent same-key commits, and a commit-versus-policy-update concurrency check.

The real ACS/Cedar study records **nine cases**:
- ACST-01: authorized staged commit occurs.
- ACST-02: ACS denies excessive amount, no effect.
- ACST-03: stage receipt tampered, no effect.
- ACST-04: target operator revokes after staging; target rejects commit.
- ACST-05: prior stage remains invalid after a later regrant.
- ACST-06: new stage under the new epoch commits.
- ACST-07: an already committed operation deduplicates after revocation.
- ACST-08: a direct call bypassing ACS still fails because the target is revoked.
- ACST-09: a caller providing the valid *claimed* principal on a direct route commits once the target is regranted. This is the required negative control exposing the missing authenticated-identity boundary.

An experiment status of `pass` means the expected outcomes **including ACST-09** were observed. It must never be interpreted as complete mediation or deployment certification.

## Formalization opportunity

This experiment suggests a bounded abstract transition relation with states
`(policy_epoch, revocation, staged_requests, committed_effects)`, where
a target commit transitions `E -> E'` only if the current target policy
permits the exact stored action. One can then verify that a revocation ordered
before the commit excludes the effect and a revocation ordered after a commit
cannot retroactively make that historical effect disappear.

To transport this result into a real deployment, the proof assumptions
would need to include authenticated caller identity, protected policy storage,
a trusted commit boundary, complete mediation over every effect pathway and
replay-safe receipt identity. These remain open obligations.

## Limits

- No mTLS, SPIFFE, signed delegation, PKI, or attested principal.
- No protection against a malicious local administrator or compromised host.
- No remote service, network isolation beyond localhost, durable distributed
  consensus, or end-to-end exactly-once guarantee.
- SQLite serializes these local commits; no claim of general linearizability
  over distributed processes or external service effects.
- The original published ACS `0.4.0a4` Cedar principal-path incompatibility
  still requires the explicit opt-in laboratory compatibility projection.
- No upstream PF or AGT project is reported as vulnerable based on these tests.

The next milestone should add an independently authenticated **target-side caller identity** and a protected policy-update authority, preserving both negative controls. That is the minimum step toward meaningful complete-mediation experiments.
