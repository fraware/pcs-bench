# Independent Ed25519 verification of agent evidence assertions

**Research component, not an authorization or effect-verification service.** The checker independently verifies two Ed25519 signatures and their cross-message bindings under a **relying-party-controlled trust configuration**. It does not independently observe a committed effect, determine whether ACS/Cedar executed, validate the policy decision's semantic correctness, or establish key custody, organizational identity, replay history or deployment security.

## Supported wire profile

This implementation supports the separate experimental protocols developed in [the existing two-root target research](https://github.com/fraware/pcs-bench/pull/1):

- Actor envelope version: `pcs-bench-ed25519-target-v1`, with the domain `pcs-bench-ed25519-target-v1\0`.
- Issuer decision version: `pcs-bench-issuer-decision-v1`, with a **different domain** `pcs-bench-issuer-decision-v1\0`.
- Action commitment version: `agent-effect-study-action-v1\0` concatenated with the exact typed action fields.
- Message serialization: sorted-key JSON with ASCII escaping and compact separators. This is **not RFC 8785 JCS**, AgenTrust TRACE or a portable canonicalization standard.
- Route: **`POST /commit` only**. A staged operation would require independent inspection of the stage's action and original authorization binding; this verifier deliberately does not assume that a stage receipt is enough.

The bytes of the received JSON envelope are parsed strictly: duplicate member keys, non-finite numbers, malformed nested values, unknown protocol fields, invalid nonce/decision IDs and oversized payloads fail closed. The signature itself is decoded under canonical unpadded URL-safe Base64.

## Verifier-owned trust inputs

`VerificationContext` is supplied by the **trusted relying party**, never copied from the submitted evidence. It includes:

- Exact target audience and current policy SHA-256/epoch.
- A trusted integer appraisal timestamp.
- Independently provisioned actor-key entries with expected principal, tenant and current active status.
- Separately provisioned issuer-key entries with expected policy SHA-256 and current active status.

The verifier checks two **different public keys**; an unknown trust-root entry yields `undetermined` instead of a fabricated authorization. Revoked keys, tampered signed content, expired/currently invalid credentials, changed policy context and mismatched actor/action/tenant/issuer relationships yield `refuted` under the **current-authorization** interpretation.

A validated pair yields `verified_assertions`. The name intentionally avoids the word `authorized`: this means the signer keys cryptographically authenticated the two mutually consistent statements **under those configured keys**, nothing more.

## Independent construction and adversarial tests

`tests/unit/test_independent_ed25519.py` uses `cryptography` directly and its own fixture encoder; it **never imports issuer or target signing helpers** from the experimental producer modules. It covers:

- Positive two-key Ed25519 signature verification;
- Altered signature/message, signer substitution, same-key actor/issuer substitution;
- Valid signatures over **different operations**, which must not be accepted as a joint assertion;
- Target audience, policy SHA-256, epoch and time changes;
- Unknown and revoked trusted keys;
- Duplicate JSON members, invalid/extra fields, wrong JSON types, oversized/recursive JSON and malformed wire encoding;
- Explicit proof that `verified_assertions` carries **no inference of issuer execution or committed external effects**.

The new package extra `.[evidence-crypto]` declares the cryptographic dependency and `.[dev]` includes it for complete test-suite execution. CI pins `cryptography==46.0.4` for experiment reproducibility and tests Python 3.11 and 3.12.

Run from a clean checkout:

```bash
python -m pip install -e ".[dev]" "cryptography==46.0.4" ruff
ruff check src/pcs_bench/independent_ed25519.py tests/unit/test_independent_ed25519.py
python -m pytest -q tests/unit/test_independent_ed25519.py
```

## Important acceptance boundaries

A valid Ed25519 credential establishes possession of the test private key by a signer at signing time **under a trusted key-enrollment assumption**. It does not establish who controlled the signing process, nor whether the person or process was authorized organizationally. Current key status here is a supplied fact, not a checked PKI revocation history.

Offline verification does not consult the target's nonce table. It cannot establish that an old signed request has not already committed, or that the current policy actually permitted the action. It is not safe to substitute this checker for the target's atomic, mutable-state enforcement.

The verifier does **not** access the producer SQLite target; it does not establish a historical committed effect, an independent effect witness, or the causal relationship between an issuer's invocation of ACS and its signed decision. Those obligations must remain `undetermined` in a general evidence-transport appraisal until independently checked.

## Next reviewable work

1. Validate the local signature-checking adapter against **cross-produced immutable records** from a separately pinned signer build, with expected digest and signature checks approved independently.
2. Add a target-owned effect observation adapter that compares a signed logical operation with a separately authenticated target state or effect oracle. Validate its observation completeness and authority independently.
3. Integrate those verified outputs with the proposition-aware temporal reliance specification in [draft PR #3](https://github.com/fraware/pcs-bench/pull/3), preserving `undetermined` for issuer-execution and current authorization where necessary.
4. Independently review cryptographic serialization, trust configuration and protocol-version compatibility before any merge.

**HOLD MERGE:** independent review, general repository CI and explicit claim-boundary checks are release gates. All generated keys in the tests are ephemeral; no key material is checked into source.
