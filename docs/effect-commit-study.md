# Executable effect-commit study

**Maturity:** local controlled research environment, not production authorization,
a security exploit, a cryptographic evidence chain, or a Lean verification result.

This study moves beyond checking policy results. An application-level reference
broker authorizes an exact request and dispatches it over **loopback HTTP** to a
separate disposable target process. The target stores committed operations and
balances in **SQLite**, in a transaction independent of the broker's response.

## Why it exists

A correct authorization verdict is not evidence that the corresponding action
was committed, rejected, or even dispatched. Likewise, a timeout can occur
after an external effect has committed.

This study explicitly compares policy decisions, broker-visible outcomes, and
target-owned state. It also demonstrates the limitation of a cooperative
broker: a direct call to a deliberately unprotected target bypasses it.

The executable target is a local testing instrument. It is **not** AGT,
Provability Fabric, OpenShell, a bank, an email service, or a production network
gateway. No real third-party effects are created.

## Reproduction

From a clean pcs-bench checkout:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/unit/test_effect_boundary.py \
  tests/integration/test_effect_commit_boundary.py \
  tests/integration/test_effect_study.py

python -m pcs_bench.effect_study --out reports/agent-effect-study.json
```

The dedicated `agent-evidence-boundaries.yml` workflow runs all these tests,
the existing pinned PF Core tests, and strict Ruff on Python 3.11 and 3.12.
It uploads a JSON report for each version as a CI artifact.

## Experimental cases

| Case | Intervention | Ground truth and expected observation |
|---|---|---|
| EFFECT-01 | Permitted action | One target-side committed effect |
| EFFECT-02 | Policy denial | No effect |
| EFFECT-03 | Change arguments after approval | No effect; broker refuses mismatched digest |
| EFFECT-04 | Revoke and increment epoch after approval | No effect; stale verdict rejected |
| EFFECT-05 | Drop the response after a durable commit | Broker says **unknown**; journal contains one effect |
| EFFECT-06 | Retry with the same operation key | Target deduplicates; zero additional effects |
| EFFECT-07 | Reuse idempotency key with changed payload | HTTP 409; zero additional effects |
| EFFECT-08 | Submit prohibited action directly to deliberately unguarded target | One unauthorized effect; illustrates a **bypass boundary** of this synthetic broker |
| EFFECT-09 | Repeat an operation using a fresh key | One additional effect; idempotency does not infer semantic duplicates |

The integration tests also submit **20 concurrent requests sharing one
idempotency key**. The transactional target must commit exactly once.

Every experiment report records the expected and observed number of new target
commits, broker or target outcome, scenario type, and final target-side
balances. It includes source-file SHA-256 digests and Python version.

The deterministic check is about **predicted behavior of the controlled
experiment**. A report status of `pass` does not say that the target's security
properties hold. In particular, EFFECT-08 is an intentional demonstration of
a broken *complete-mediation assumption*, and its observed commit is the
expected experimental result.

## Boundary definitions

- **Authorization:** `pcs_bench.effect_boundary.decide` evaluates a
  caller-supplied immutable `Policy`. It has no authentication or distributed
  authorization authority. The evaluator trusts the supplied policy object.
- **Action identity:** versioned SHA-256 commitment to explicit actor, tenant,
  resource, integer delta, and operation ID; not an RFC 8785 record, not a
  cryptographic signature, and not a globally trusted authorization token.
- **Dispatch:** the broker checks the exact committed request digest, policy
  epoch, and current local policy snapshot immediately before its HTTP call.
  There is no post-dispatch revocation handshake or target-enforced policy.
- **Effect oracle:** the disposable target's journal and balances reside in a
  SQLite database controlled by another local process. The agent-side response
  and target journal are observed through different code paths. Target
  authenticity and log-completeness against a malicious host are **not** proven.
- **Idempotency:** SQLite serializes writes with `BEGIN IMMEDIATE`; an
  operation ID is unique and payload-bound. Reusing the key with a modified
  payload produces a conflict. Changing the key permits another effect.
- **Unknown outcomes:** a lost reply **does not** mean the operation failed.
  The client reports `unknown`; the separate target query later establishes
  that the local target committed the operation.
- **Isolation:** loopback-only development HTTP server. Direct access is
  intentionally available to exhibit the limitation of application-level
  mediation. Never deploy this server exposed to another host.

## Limitations and next implementation targets

The first study checks process-separated evidence and effect state, but not
authenticated independent witnesses, filesystem or kernel-level mediation,
TEE attestation, trusted policy distribution, pre-commit reauthorization at
the target, distributed two-phase commit, external policy engines, or
independent Lean proof verification.

The next work should replace the reference policy/broker with **one actual AGT
or PF adapter**, preserve the exact experimental effect oracle, then compare
with a sandbox-enforced path (for example OpenShell). This needs explicit
adapter-version pinning and a separately reviewed execution threat model.

Also test revocation between dispatch and target commit, not only between
approval and dispatch. That would require a target-side authorization
handshake, decision freshness constraints, and a meaningful commit boundary.

Finally, integrate the experiment into the published benchmark vocabulary
only after its metric semantics and applicability are independently reviewed.
A single scalar security score would conceal the distinction between correct
denials, good effects, ambiguously observed effects, and actual unauthorized
commits.

## Verification snapshot

The dedicated workflow completed successfully on October 18, 2026 for
`fraware/pcs-bench@74b09fc5f83298cc4794b722e42e8db66dc08ec1`:
**44 tests passed on Python 3.11 and 44 tests passed on Python 3.12**, with
Ruff passing on both and machine-readable study reports uploaded as artifacts.
See [the actual workflow](https://github.com/fraware/pcs-bench/actions/runs/39160693254).
This is evidence of the experiment implementation working under its declared
conditions, not evidence of real-world deployment or upstream security.

The general repository-wide PCS Benchmark workflow is independently failing
on baseline lint/test debt that is not part of this study; the research PR
is intentionally open and has a HOLD MERGE review gate.
