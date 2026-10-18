# Real ACS/Cedar policy decisions versus independently observed effects

**Status:** experimental, pinned native-policy integration. This is not an
upstream security advisory, a production enforcement mechanism, or an
attestation of all agent effects.

This study runs the published
[`agent-control-spec==0.4.0a4`](https://pypi.org/project/agent-control-spec/0.4.0a4/)
Python extension and its transitive Agent Hooks SDK. A real Cedar policy
(under `tests/fixtures/acs_effect`) is evaluated at the actual
`pre_tool_call` intervention point. The emitter is explicitly set to
`EnforcementMode.ENFORCE`.

The small reference host compares approval against an action digest and a
host-owned policy epoch, re-evaluates the genuine Cedar policy at dispatch,
and invokes a separate loopback HTTP target process. This target writes
its own durable SQLite journal and intentionally does not enforce policy.

## Reproduction

```bash
python -m pip install -e ".[dev]" "agent-control-spec==0.4.0a4" ruff
python -m pip check
ACS_EFFECT_INTEGRATION=1 python -m pytest -q tests/integration/test_acs_effect_host.py
python -m pcs_bench.acs_effect_study --out reports/acs-effect-study.json
```

The dedicated CI workflow executes Python 3.11 and 3.12, checks the exact
package version, applies strict Ruff lint, runs the integration probes and
uploads machine-readable reports.

## The pre-release compatibility boundary

In the published `0.4.0a4` Cedar dispatcher, the principal is resolved
from `envelope.agent.id`, while Agent Hooks 0.1 standard contexts place
it at `agent.id`. As a result, an unmodified otherwise-permitted Cedar
call fails closed with `runtime_error:policy_invocation_failed`.

This is an upstream, known snapshot-shape bug subsequently addressed in
the [ACS changelog for 0.4.0-beta.1](https://github.com/responsibleai/agent-control-spec/blob/main/CHANGELOG.md).

The test host has an explicit **opt-in non-normative compatibility
projection** that copies the already constructed *host-owned* agent ID
from `agent.id` to `envelope.agent.id` for this pinned alpha release.
It does not derive the identity from the tool request. A regression test
requires the original unmodified path to fail closed.

The compatibility projection is only appropriate for this pinned
experiment. Remove it and rerun the standard-context tests against a
verified published release containing the fix; do not silently carry a
nonstandard field into production. The source package's later
implementation is distinct from the tested alpha wheel.

## What is actually enforced

1. The host owns the authenticated-context *representation* and a monotone
   per-session Agent Hooks sequence. The experiment's identity value is a
   fixture, not externally authenticated.
2. Cedar explicitly denies mismatching principal, tenant, resource,
   out-of-range integer delta and host-supplied revocation flag; its
   `@id` reasons are asserted in positive and negative tests.
3. A positive policy result can be dispatched only if the exact action
   digest and host policy epoch still match. The host re-evaluates the
   current Cedar decision before calling the target.
4. The target records committed effects independently of the broker's
   reported success, with idempotency enforced by SQLite.
5. A reply lost after a durable commit is `unknown` at the host, even
   though target-state inspection subsequently finds the commit.
6. A prohibited action sent directly to the deliberately unmediated
   target commits successfully. This demonstrates an architectural
   limitation of a cooperative host, **not** a vulnerability in ACS.

The report identifies the ACS package version, SHA-256 of the manifest
and policy, whether the compatibility projection was used, individual
expected and observed effects, and the final target-owned ledger.

## What it does not establish

- That the host has *complete mediation* over every tool, network, shell,
  filesystem, or external-service path.
- That an authorization check is valid at the moment of *external commit*
  if revocation happens after dispatch.
- That externally authenticated principals or trust roots back the
  constructed local identities and policy state.
- That a successful Cedar verdict implies a committed external effect.
- That the observed target is independent of the process owner or
  protected by cryptographic attestation.
- That the policy semantics or security of any real deployment has been
  independently certified.

The next experiment should connect a real ACS/PF-governed dispatch to an
effect target with an independently enforced operation boundary, then
test revocation between authorization and commit and targeted bypasses.
The existing direct-call negative control is intentionally kept as a
reference point.

## Interpretation and review

**PASS** for the experimental study means that both the permitted and
denied controls, timeout/replay cases, and intentionally unmediated
negative control matched the observable local ledger. It is not a
statement that all actions were prevented or that the system was
secure in a deployment.

See also [cross-repository conformance](agent-evidence-boundaries.md) and
[baseline effect-commit study](effect-commit-study.md).
