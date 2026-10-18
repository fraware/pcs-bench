# Verifier-relative reliance transport: reference acceptance contract

**Status: research reference implementation.** This is not a signature verifier, a policy engine, an issuer attestation, an effect observer, an authorization token service, a Lean proof or a security certification.

## Core question

Can an evidence-backed claim about an autonomous agent still be relied on after its policy, issuer key, actor key, target, verifier implementation, observation source or effective trust context changes?

Not automatically. An authentic historical certificate may fail to support current reliance. The conservative appraiser requires **freshly executed, independently trusted verifier callbacks** under the exact current reliance context. Claim-provided flags never count.

## Five separate obligations

| Check | Required independent evidence |
| --- | --- |
| actor_signature | A valid actor signature over the intended request under the current trusted key |
| issuer_signature | A valid independent issuer signature over the intended decision under the current trusted issuer key |
| policy_result | The named policy and evaluation inputs actually support that decision |
| issuer_execution | Independent grounds that the issuer executed that evaluation, not merely that it signed an allow statement |
| effect_observation | An independently trusted observation of the committed effect bound to the exact action and receipt |

This module **does not perform these checks**. The caller must configure real trusted verifier implementations and supply them as callbacks. The unit tests use synthetic callbacks to test decision logic, not cryptographic security.

In particular, replaying the policy with the same ACS SDK may be useful for policy_result but does not establish issuer_execution. The configuration requires distinct verifier identities for those two checks.

## Types and decision semantics

The Claim type binds an operation, action digest, audience, policy source hash and epoch, actor and issuer key fingerprints, effect receipt digest and validity period.

The CurrentTrust type supplies the current intended action, target, policy, keys, observation source and five verifier identities/versions. Its domain-separated SHA-256 digest identifies the reliance context. Each callback result must be bound to this exact claim and current context. Neither fingerprint nor binding digest is a signature.

The outcomes are:

- **accepted:** all structural anchors match; validity holds; all five current trusted verifiers return established under the matching identity, version and binding.
- **rejected:** a structural trust assumption has changed, the claim is outside its validity period, or any current trusted verifier explicitly refutes its obligation.
- **undetermined:** a required verifier is missing, unavailable, stale, reports unknown or otherwise provides no usable result.

A refutation takes precedence over incomplete checks. A missing external effect oracle is never interpreted as proof of a missing effect. A changed policy epoch or issuer key rejects current reliance on an older claim; it does not imply the historical issuer behaved maliciously.

The callbacks themselves are an **explicit trust assumption**. An untrusted agent able to supply a fake callback returning established could defeat the appraiser. Therefore, this program must not be exposed as an authorization endpoint accepting attacker-selected verifier code.

## Reproduction

Run the path-scoped CI workflow or from a clean checkout install the development dependencies, then run Ruff and pytest on only the new module and test file:

- src/pcs_bench/reliance_transport.py
- tests/unit/test_reliance_transport.py

The dedicated workflow tests Python 3.11 and 3.12. Existing repository-wide Ruff failures do not disappear.

## Scope and interpretation

Under a trusted current context Gamma and trusted verification functions V_i, the reference rule accepts only when the structure and time are valid AND every configured V_i establishes its obligation against the **current** context.

That is an explicit decision predicate, not a mathematical proof of the external checkers or of system security. This module does not inspect signed TRACE records, verify Ed25519, replay a real Cedar policy, independently witness issuer execution or attest target commits. The absence of those external verifier adapters must be reported as **undetermined**, not accepted.

## Next useful implementation

Implement separately pinned verifier adapters for real actor/issuer signatures and independently instrumented effect observations; introduce an execution witness separate from a replayed policy result. Construct paired-world experiments holding evidence constant while changing verifier versions, policy sources, issuer trust and target observation channels. Measure false preservation and unnecessary revalidation. Finally, formalize a bounded refinement theorem with an explicit proof-to-code mapping.

Keep the earlier large ACS/target experiment unmerged and separate; this small module is intended to be independently reviewable from main.
