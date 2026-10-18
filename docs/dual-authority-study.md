# Two-root authorization at the actual effect commit boundary

**Research status:** independently signed, separately appraised authorization is implemented in a disposable local target. It is not a production entitlement service, hardware-backed trust, cryptographic proof that Cedar ran, a complete mediation result, or a machine-checked end-to-end theorem.

## What problem this solves

The earlier Ed25519 target authenticated a caller and checked the target's own coarse-grained policy. A registered actor could still submit an otherwise-permitted action directly, bypassing the ACS host.

`src/pcs_bench/dual_authority_target.py` is a **separate target process** with no actor-only effect route. It requires:

1. A caller-signed Ed25519 request bound to the exact route, body, registered actor key ID, principal, tenant, nonce, target-specific audience, and validity interval.
2. A **different trusted policy issuer's** Ed25519 `allow` decision bound to the same actor key ID, principal, tenant, exact action digest, target audience, pinned policy-file SHA-256, current target policy epoch, unique decision identifier, and a short expiry.
3. A target-owned policy whose resource, amount, revocation, and epoch obligations remain satisfied at commit.

The signatures and the required fields are reappraised inside a target-owned `BEGIN IMMEDIATE` SQLite transaction. A new effect and its decision-attribution record are inserted within that same transaction. Operator key and policy revocations serialize with commits.

The actor and issuer have separate key registries and **must possess distinct public keys**. A caller cannot provide its own issuer public key via the HTTP API. Policy enrollment/revocation requires trusted local SQLite operator access.

The `/stage` route is authenticated by the actor but is non-effecting. `/commit-staged` requires both signatures and rechecks staged action ownership and policy epoch. A direct `/commit` also requires both signatures.

A committed operation may be queried or idempotently deduplicated using a fresh actor nonce and a still-valid permission. Replaying the exact signed actor request is rejected. Reusing a decision ID for a different operation is rejected.

## What is actually tested

The standalone integration tests cover both positive and negative controls:

- Valid independently signed caller and permission produce one target-owned ledger effect.
- Correctly signed caller **without** a policy permission cannot commit.
- Unknown policy issuer and a caller pretending to be the policy issuer are rejected.
- Reusing the same Ed25519 public key as both actor and issuer is forbidden.
- Caller key/identity, action content, issuer policy hash, target audience and token validity must match the locally trusted context.
- Revoked actor keys, revoked policy issuers, and obsolete policy epochs cannot authorize a new effect.
- Even an issuer-signed `allow` cannot bypass the target's current resource/amount restriction.
- Original actor nonces cannot be replayed, while a fresh nonce for the already-committed operation is deduplicated.
- One registered actor cannot reuse a second actor's policy token or staged ownership.
- A stage requires the independent policy decision **at final commit**, including when the target policy changed after staging.
- Concurrent replayed credentials produce one new effect.
- A policy decision ID cannot be recycled to authorize a different action.

The real ACS experiment in `src/pcs_bench/dual_authority_acs_study.py` uses the pinned published `agent-control-spec==0.4.0a4` package. The trusted test issuer calls real ACS/Cedar under enforcing Agent Hooks, then signs an `allow` for that exact action, while the target checks the independent issuer signature and target-owned policy. The ACS alpha4 principal-path compatibility projection remains explicitly enabled, recorded, and test-only.

A deliberate negative control is preserved: the **trusted issuer itself** may sign a seemingly valid token without calling ACS. The target verifies the signature and associated fields, but it cannot determine from the signature whether the issuer actually executed the purported policy engine. This is a precise remaining issuer-honesty and software-measurement assumption.

## Reproduction

```bash
python -m pip install -e ".[dev]" "cryptography==46.0.4" ruff
python -m pytest -q tests/integration/test_dual_authority_target.py

python -m pip install "agent-control-spec==0.4.0a4"
ACS_EFFECT_INTEGRATION=1 python -m pytest -q \
  tests/integration/test_dual_authority_acs.py
python -m pcs_bench.dual_authority_acs_study \
  --out reports/dual-authority-acs.json
```

Dedicated CI runs Python 3.11 and 3.12 and uploads a machine-readable report for both environments. No private signing key or production credential is committed to Git.

## Cryptographic and trust boundaries

The actor and decision record have **different domain-separated byte encodings**. Their construction is specific to this research fixture and **not** RFC 8785 JCS, AgenTrust TRACE, SCITT, or an independent proof of policy semantics. A SHA-256 policy digest pins bytes, not the policy's soundness. The experiment assumes honest local key enrollment and protected operator state, a trustworthy monotone-enough server clock within the specified skew, cryptographic correctness of the Ed25519 library, complete mediation for effects **inside this particular service**, and proper control of the distinct private keys.

The policy-issuer private key resides in a separate *logical authority role* and is not handed to the target; these experiments do not prove machine or hardware separation between those roles. Signing a permission is an issuer statement, not a zero-knowledge execution proof of ACS. The unprotected local HTTP transport means this system must remain localhost-only: no TLS/mTLS, workload identity, host compromise defense, remote attestation, PKI trust chain, globally consistent revocation, independent transparency witness, or real-world exactly-once guarantee is provided.

A report `pass` means positive and negative synthetic outcomes matched target-owned SQLite observations; it must **never** be interpreted as a deployment security certification.

## Remaining high-value work

1. A separate, constrained policy-decision issuer service or process with independent enrollment and measured software identity. Evaluate against malicious/compromised issuer behavior and explicit trust assumptions.
2. Give the relying party independently authenticated, omission-detectable effect receipts (for example, a witnessed append-only checkpoint).
3. Stress-test clock rollback, token expiry during final commit, key rotation and revocation races, concurrency under multiple principals/issuers, and malformed canonical encodings.
4. Formalize a bounded statement about the two-signature commit transition, with the exact trust assumptions and a proof-to-code mapping, without claiming the Lean kernel verifies the external crypto or SQLite engine.
5. Reconcile the broad repository CI and obtain independent methodology and implementation review before merge.
