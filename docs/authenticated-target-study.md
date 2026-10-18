# Ed25519-authenticated target effects — experimental identity boundary

**Status:** local research implementation, not a production identity provider,
security certification, cryptographic attestation, or proof of complete agent
mediation. The original self-asserted guarded target remains as a separate
negative-control system; this experiment runs a **different** target process.

## What is actually implemented

`src/pcs_bench/authenticated_target.py` enforces requests signed by an Ed25519
private key. The target stores only the 32-byte public key in a SQLite key
registry provisioned through **trusted local operator access**, alongside the
associated principal and tenant. No HTTP operation can enroll or revoke a key.

Every protected POST is bound to:
- Exact method and path (`POST /stage`, `/commit-staged`, or `/commit`).
- A per-database random target audience, unique across fresh target instances.
- A registered key ID, an Ed25519 signature and a domain-separated serialized
  request body.
- A 128-bit random nonce, issuance timestamp and expiry of at most 60 seconds.
- The exact requested action or staged receipt, then the target's *current*
  policy, including revocation and allowed resource and amount.

Target-side verification of the signature, public-key revocation state,
nonce uniqueness, principal/tenant mapping, stage ownership, current resource
policy and new effect insertion all occur within a single SQLite
`BEGIN IMMEDIATE` transaction. A concurrent operator policy/key update
therefore has a well-defined order relative to a commit in this database.

A replay of the **same signed request** is rejected. Repeating a completed
logical operation with a **fresh signed nonce** returns a deduplicated result
without a new balance update, provided the signing key remains valid.

The signed wire envelope uses **PCS Bench Ed25519 Target v1** domain separation
and a local sorted-key JSON serialization. It is not RFC 8785 JCS or a TRACE
attestation record, and this study does not assert general interoperability
with those formats.

Private keys are generated inside tests and never committed to the repository
or persisted in the target database. The signer's keys are test credentials,
not a deployed organizational trust root.

## Reproducible tests

```bash
python -m pip install -e ".[dev]" "cryptography==46.0.4" ruff
python -m pytest -q tests/integration/test_authenticated_target.py
```

The dedicated GitHub Actions workflow runs this suite on Python 3.11 and 3.12.

The tests cover:
- Legitimate authenticated commit and independently recorded key attribution.
- Rejection of unsigned calls, unregistered keys, altered signatures and
  caller-controlled principal/tenant impersonation.
- Cross-target audience mismatch, cross-route signature misuse and malformed
  JSON with duplicate object keys.
- Expired/future credentials and excessive validity windows.
- Nonce replay, fresh-nonce idempotency, same-key altered action collisions,
  20 concurrent replays and 20 concurrent fresh signed nonces.
- Target policy and key revocation **after** staging but **before** commit.
- Stage-receipt mutation, attempted takeover by another registered signing key,
  and absence of an HTTP administrator endpoint.

## Real ACS/Cedar integration

`src/pcs_bench/signed_acs_study.py` runs the published native
`agent-control-spec==0.4.0a4` Cedar policy under Agent Hooks enforcing mode.
The host generates a policy decision; separately authenticated target
requests perform staging and commit.

A ten-case JSON report tests: authorized effect, Cedar denial, unsigned
forgery, signed identity mismatch, replay, target policy revocation between
staging and commit, stale grant rejection after reauthorization, a new-epoch
commit, direct signed invocation bypassing ACS, and key revocation before
commit. The report records source-policy hashes and target-owned effect
state, while excluding private signing keys.

The ACS alpha4 principal-path incompatibility remains handled by an explicit
opt-in test compatibility projection. That projection is not a proposed
production Agent Hooks extension.

## What this does not prove

**A valid key is not equivalent to an ACS authorization.** The target's
coarse-grained policy still allows a direct *correctly signed* operation that
bypasses the ACS host. This remains an explicit negative-control case.
To prevent that class, the target would need a separately appraised ACS
authorization token bound to action digest, principal, policy epoch and
expiry, or equivalent mediated capability architecture.

The signature authenticates possession of the enrolled test key, **not**
the physical person or underlying AI instance, and no TLS/mTLS or SPIFFE
workload identity is deployed. No hardware-backed key management, remote
attestation, compromise resistance, distributed authority, secure clock,
PKI-based revocation, or proof of independent ledger completeness exists.

The target remains loopback-only. Public journal reads are intentionally
available to the local test evaluator; no independent signed append-only
transparency witness is implemented.

The formal guarantee is limited to the executable local SQLite model:
given its trusted policy store and enrolled keys, a newly committed effect
is recorded by a transaction that successfully verified the request
signature, exact identity and current target policy. Test results
support this bounded implementation claim; it is not a Lean proof of
the cryptographic or OS-level trusted computing base.

## Priority after this milestone

1. Bind the target to an independently authorized, narrowly attenuated
   **ACS policy decision**, not just a valid registered client signature.
2. Verify action identity and policy epoch **again inside the target's final
   commit transaction**, using a second trust root distinct from the actor.
3. Test key compromise and rotation, multi-tenant provisioning, repeated
   retries, and revocation after dispatch.
4. Audit the target journal under an independently anchored checkpoint so
   the relying party can identify omitted or rewritten evidence.
5. Add a small refinement proof that expresses exactly the tested state
   transition property, without claiming to prove the complete deployment.
