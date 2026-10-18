# Agent evidence boundary conformance — initial pinned-source study

**Status:** diagnostic research harness; not a security certification, production
vulnerability report, formal proof, or release authorization.

This experiment adds four logically separate evidence comparisons to pcs-bench.
It deliberately leaves the governance, runtime, and formal-kernel repositories
unchanged. It evaluates a pinned version of
[SentinelOps-CI/provability-fabric-core](https://github.com/SentinelOps-CI/provability-fabric-core)
at commit `b853bea6d79a6c683928031885176efef851aa5a`.

## What is and is not checked

| Case | Subject | Required independent input | Current evidence boundary |
|---|---|---|---|
| AUTH-01 | Principal/capability reconstructed by the PF sidecar normalizer | Separately provisioned effective grant for principal and tenant | A capability reported by a sidecar is not itself an authenticated grant |
| SCOPE-02 | Capability `resource_pattern` compared with declared resource URIs | Independent capability catalog | Base PF-Core `action_allowed` omits pattern matching; stronger checks exist elsewhere |
| EFFECT-03 | Recorded read/write resource footprint compared with independent inventory | Authoritative access footprint | Reference normalization currently records a file-write target under `reads` |
| PROOF-04 | Lightweight `Lean-proved` certificate versus PCS `LeanKernelChecked` | Actual independent proof binding and kernel verification | Matching a label or theorem filename is not checking a concrete proof |

The report uses three values:

- `consistent`: supplied objects agree **under the caller's trust assumptions**.
- `contradicted`: supplied objects disagree with the declared property.
- `insufficient`: the required independent evidence is absent or cannot be
  established by this checker.

The aggregate result is contradicted if any component is contradicted,
insufficient if any component is insufficient and none is contradicted, and
consistent otherwise. Even a fully consistent result **does not prove**
independent grant authenticity, runtime effect commitment, trace completeness,
or theorem checking. It must never be interpreted as permission to execute.

The implementation is in `src/pcs_bench/evidence_boundary.py`. It intentionally
does not fetch untrusted URLs, consult mutable external state, or use an LLM to
judge authorization.

## Reproduction

Run standalone unit tests:

```bash
pip install -e ".[dev]"
python -m pytest -q tests/unit/test_evidence_boundary.py
```

Run pinned upstream-source probes:

```bash
git clone https://github.com/SentinelOps-CI/provability-fabric-core.git external/pf-core
git -C external/pf-core checkout b853bea6d79a6c683928031885176efef851aa5a
export PF_CORE_REPO="$(pwd)/external/pf-core"
python -m pytest -q tests/integration/test_pf_core_evidence_boundary.py
```

On each PR changing these files, `.github/workflows/agent-evidence-boundaries.yml`
checks out the exact upstream SHA and runs the conformance probes with Python
3.11 and 3.12. The job does **not** use `continue-on-error`; if the pinned
source cannot be fetched or the observed behavior differs, the check fails.

The normal pcs-bench test suite skips only the optional pinned-source module
when `PF_CORE_REPO` is absent. The dedicated workflow always supplies that
variable, and the module requires the checkout to exist.

## Interpretation of the pinned tests

The tests show that a reference normalizer populates roles and capabilities
from action-side fields, that the base decider can accept a same-tenant URI
outside the capability pattern, that file-write normalization loses write
classification, and that the lightweight emitter's label is not sufficient
for `LeanKernelChecked`.

These are *reproduced code-path distinctions*, not confirmation of a
production exploit. The adapter is documented upstream as untrusted and the
PF Core proof boundary expressly excludes completeness of external
enforcement. PCS Core's newer `TraceSafeRCertificate` and release-grade
signature gates provide additional controls; they must not be confused with
the legacy PF-Core emitter.

The pinned probes currently **characterize** behavior; they do not require
the upstream reference adapter to be fixed. When an upstream repair is ready,
create a new pinned target and replace the corresponding observation test
with a normative rejection/acceptance test. Keep old pins available as
historical regression baselines.

## Trust and semantic boundaries

1. `independent_grant` must come from a separately authenticated identity
   and authorization source. Passing a self-asserted object proves nothing.
2. `trusted_catalog` is separately provisioned; the normalizer's own
   `resource_pattern` is not an authoritative source for authorization.
3. `independent_footprint` must come from a trusted target-side or mediation
   instrument. Checking its equality to an agent-generated report is inadequate.
4. `proof_claim_consistency` only checks that a legacy claim cannot be
   structurally promoted. It deliberately **does not** accept any
   `LeanKernelChecked` object as proof of a checked Lean term. The actual PCS
   proof-binding verifier and trust-root policy must run independently.
5. The resource-scope matcher deliberately implements lexical `*` globbing.
   Actual URI normalization, filesystem traversal, system-call aliases, and
   network egress controls are outside this comparison.

## Next experiments

- **AUTH-05:** approval bound to one canonical request, then arguments or
  policy epoch change before execution.
- **EFFECT-06:** independently commit a write to a disposable target; compare
  dispatch, authorization, response, and target-side observation.
- **RETRY-07:** commit followed by timeout and workflow restart, with
  idempotency and outcome reconciliation.
- **TRACE-08:** verify source-native PCS and AgenTrust TRACE digest rules
  independently; require a loss-aware and typed bridge.
- **MEMORY-09:** invalidate a scientific claim after a correction while
  preserving its authentic historical verification.

Results from this harness should be reported with upstream commits, the
source of each independently supplied evidence object, exact test commands,
and a distinction between simulation, runtime checks, Lean proof checking,
and external effect evidence.
