# Temporal evidence reliance — specification v1 (experimental)

**Status:** proposed, author-labeled, unreviewed reference semantics. This document and its executable model are not a security certification, a proof of external policy execution, a verification of a signature, or a benchmark with independently confirmed ground truth.

## Purpose and claim

A prior positive evaluation of a proposition may remain usable when the applicable trust context changes. Whether it remains usable depends on **the proposition**, **which dependency changed**, and **when the change became effective**. In particular, a later revocation of authority does not by itself erase a previously observed event.

This specification separates a **reliance/transport decision** from the actual **truth status** of the underlying proposition.

It does **not** replace the draft verifier-relative acceptance contract in PR #2. That contract presently checks exact current context and five trusted callbacks; this specification defines a candidate temporal layer to guide its future revision. PR #2 remains unchanged.

## Proposition taxonomy

| Proposition | Informal intended meaning | Reference time |
|---|---|---|
| `historical_occurrence` | A particular effect occurred | Event time, with evidence assessed now |
| `historical_authorization` | That operation was authorized under the then-applicable authority | Event time |
| `policy_decision_correctness` | The policy applicable to a specified historical decision supported its recorded outcome | Pinned evaluation time and input |
| `issuer_execution` | The issuer actually executed the claimed policy evaluation | Evaluation occurrence time, with evidence assessed now |
| `current_authorization` | The operation is permitted in the present trust context | Current appraisal time |

These are distinct propositions; a confirmed historical occurrence does not prove historical or present authorization. A mathematically valid issuer signature does not prove issuer execution.

## Reference decision values

- `preserve`: the previously established appraisal may be reused **under the supplied trusted oracle assumptions**, because the change is irrelevant, not yet effective, post-event for the relevant historical authority, or independently bridged.
- `reappraise`: do not reuse the old positive result. Its truth is undetermined from the changed context alone; acquire and check relevant new evidence.
- `withdraw`: a **trusted independently verified refutation** makes previous affirmative reliance inadmissible for that proposition and time. Withdrawal is not a claim that a historical event never happened.

This is a **single-change** reference model, not a complete temporal logic, an authorization protocol, or a proof of semantic equivalence of verifier versions. Cases assume the earlier positive result was valid under the earlier context.

## Input assumptions and trust boundary

Each fixture has one proposition, an `event_at` and `appraisal_at` integer, and a changed dependency identified by type, change mode, and `effective_at`.

Two additional values are deliberately evaluator-trusted:

- `verified_bridge`: an independent authority has established that the specific change preserves the proposition-relevant obligation. Source and proof of this fact are **outside** v1.
- `verified_refutation`: independent trusted grounds conclusively refute the prior affirmative reliance for this precise proposition and effective time. Source and proof are **outside** v1.

**These flags must never be copied from a claim, signed issuer statement or attacker-supplied request.** Their appearance in the fixtures is a transparent modeling assumption, not a cryptographic verification.

A high-assurance real-world evaluator must replace these Boolean inputs with independently checked evidence, including scope, effective time, trust root and verifier identity.

## Exact single-change transition rule

1. Reject malformed data and contradictory verification assumptions.
2. If the change becomes effective *after* appraisal, preserve prior reliance for now.
3. If the changed dependency does not support this proposition, preserve.
4. For `historical_authorization`, `policy_decision_correctness` or `issuer_execution`, a policy or actor/issuer-key authority change effective **after the referenced event** does not retroactively change the then-applicable authority or the historical occurrence of issuer execution. Preserve, unless additional evidence establishes a different effective historical fact (which must be represented with the correct earlier effective timestamp).
5. If a relevant verified refutation applies, withdraw.
6. If a relevant independently verified transport bridge applies, preserve.
7. Otherwise, reappraise.

The rule distinguishes missing evidence from contradictory evidence: an unavailable witness requires reappraisal; it does not prove the negative. It treats a verified bridge as an explicit independent premise; there is no algorithm here to determine whether two versions of a policy or verifier are equivalent.

In this v1 model, changes to an external effect-observation channel are relevant to historical occurrence even when detected after the event. This is because the **current evidentiary reliability** of the event may have changed, not because the external event itself can be retroactively altered.

## Independently inspectable fixture set

`benchmarks/temporal_transport/v1/cases.json` contains **32 author-labeled cases**, each with a short semantic rationale. It covers all five proposition types, eight dependency categories, future-effective changes, post-event revocation, retroactive compromise assumptions, lost observations, independently verified bridges and refutations.

The labels were assigned in the dataset separately from the executable `evaluate` function. They are **not independently reviewed ground truth**; their purpose is to expose our semantic hypotheses to external scrutiny.

The unit tests validate that the implementation matches those hand-written expectations and check additional invariants. This is the first reference implementation for a future benchmark, not a claim of statistically representative coverage.

## Reproducibility

```bash
python -m pip install -e ".[dev]" ruff
ruff check src/pcs_bench/temporal_reliance.py tests/unit/test_temporal_reliance.py
python -m pytest -q tests/unit/test_temporal_reliance.py
```

Dedicated CI should run Python 3.11 and Python 3.12 from the exact branch SHA, with source-pinned dependencies and available artifacts. The repository-wide PCS Benchmark failure is a separate workstream and must remain disclosed.

## Review questions / open limitations

1. Is a prior *authorization* best modeled at the instant of issue, dispatch or final committed effect? The current fixture uses a single event time and cannot express all three.
2. How should a later-discovered compromise of an issuer's key affect signatures made before its disclosure? Its **verified compromise-effective time** matters; disclosure time alone is not enough.
3. Which changes genuinely affect *policy-decision correctness* for a pinned historical source/input, and which affect only its evidence or a future policy?
4. What minimum evidence supports an independently verified bridge across a new verifier implementation?
5. How should trust changes with multiple interacting causes be combined? This reference model has exactly one change.
6. What independent ground-truth oracle and reviewers will confirm fixture labels before scientific metrics are published?

These questions must be answered before upgrading the v1 contract into a general evidence-transport theory or publishing claims about soundness, completeness or false preservation.

## Related baselines

See [frozen research baselines](../research-baselines-2026-10-18.md). The earlier evidence-and-effects PR #1 remains open and unmerged, as does verifier-relative acceptance PR #2. Neither is modified by this separate branch.
