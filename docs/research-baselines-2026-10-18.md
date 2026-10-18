# Frozen research baselines — October 18, 2026

This manifest records independently queryable GitHub facts and establishes comparison anchors. It does **not** certify scientific correctness, third-party trust, production readiness, or completeness of the test coverage.

| Reference | Immutable revision | Evidence | Result |
|---|---|---|---|
| `main` | `6092cccefee7841dfde1393e6881d433838a2252` | [Actions 26524516260](https://github.com/fraware/pcs-bench/actions/runs/26524516260) | Failed: unit/integration tests on Python 3.11; 3.12 cancelled; dependent jobs skipped |
| [Agent-effect research PR #1](https://github.com/fraware/pcs-bench/pull/1) | `423aa6d8682117474b22dd960da62b490f148361` | [Dedicated Actions 39169217343](https://github.com/fraware/pcs-bench/actions/runs/39169217343) | Dedicated Python 3.11/3.12 checks pass; [broad Actions 39169217324](https://github.com/fraware/pcs-bench/actions/runs/39169217324) fails at Ruff |
| [Reliance reference PR #2](https://github.com/fraware/pcs-bench/pull/2) | `eb03d7102b3f97c304fa4fe0291eb103a7a6549c` | [Dedicated Actions 39170734581](https://github.com/fraware/pcs-bench/actions/runs/39170734581) | Dedicated Python 3.11/3.12 checks pass (30 tests/version); [broad Actions 39170734791](https://github.com/fraware/pcs-bench/actions/runs/39170734791) fails at Ruff |

Both research PRs remain open and unmerged. PR #1 contains 37 changed files and 80 commits, and PR #2 contains four changed files and nine commits as checked. Neither has recorded independent review approval. The `main` branch was not protected when checked.

## Critical interpretation

1. Dedicated checks demonstrate reproducibility of their declared local tests; they do **not** verify complete security or formal correctness.
2. PR #1 tests real published ACS `0.4.0a4` with a test-only snapshot compatibility bridge, against locally controlled effect targets and issuer processes. It does not establish that a trusted issuer actually executed ACS in a given production environment.
3. PR #2 is a reference acceptance predicate. Its positive callbacks are **synthetic**, not independently verified signatures, actual issuer-execution witnesses or externally authenticated effect observations.
4. The full workflow on `main` failed at unit/integration testing. Research-branch broad workflows fail sooner on lint. These are distinct failures and must be diagnosed separately. Broad producer/simulation gates are not known to pass.
5. The old positive outcomes must not be silently reinterpreted as proof of current authorization, historical occurrence, or scientifically valid transport across trust changes.

## CI recovery procedure (separate PR)

From clean `main`, first execute `ruff check src tests` and `python -m pytest -q` as **independent commands** under a pinned Python environment. Capture their stdout/stderr, complete test inventory, package versions, and deterministic source SHA. Do not use a lint fix to conceal a failing test; do not use `continue-on-error` to turn a mandatory quality gate into an optional report.

Classify any semantic lint correction separately from formatting-only changes. Once the original test suite passes, run the producer-offline and simulation workflows and inspect their artifacts. Reproduce the final candidate on both Python 3.11 and 3.12. Establish repository branch protection **after** checks are stable and appropriately scoped. Review and merge require separate approval; this baseline manifest does not waive either condition.

## New development isolation

New temporal semantics, hand-labeled cases, and regression tests belong to `spec/temporal-reliance-v1`, based directly on the frozen `main` SHA, not stacked on PR #1 or PR #2. The original branches should remain unchanged during this specification experiment. All test case labels are benchmark hypotheses subject to independent review, not external ground truth.
