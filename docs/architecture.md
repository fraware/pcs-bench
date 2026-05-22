# Architecture

pcs-bench is an evaluation harness that orchestrates the PCS ecosystem from the outside. PCS schemas, certificates, workflows, admission logic, and rendering remain in their home repositories.

## Evidence chain under evaluation

```
runtime evidence
  -> certificate or witness
    -> certified claim bundle
    -> verifier admission
    -> signed science claim bundle
    -> formal trust-envelope check
    -> scientific-memory import and rendering
```

## Repository layout

| Path | Role |
|------|------|
| `benchmarks/` | Suite definitions, cases, fixtures |
| `src/pcs_bench/` | Harness implementation |
| `src/pcs_bench/adapters/` | CLI wrappers per ecosystem repo |
| `src/pcs_bench/pipeline/` | Declarative per-workflow stage lists |
| `src/pcs_bench/schemas/json/` | Embedded JSON Schema fallbacks |
| `tests/fixtures/producer_ingest/` | Reference producer ingests for offline gates |
| `scripts/` | Fixture materialization and schema sync |

## Execution modes

| Mode | Flag | Behavior |
|------|------|----------|
| Simulate | `--simulate` (default) | Expected outcome files plus artifact analysis |
| Live | `--live` | Invokes ecosystem CLIs |
| Hybrid | `--hybrid` | Live first, then expected outcomes when CLIs are missing |
| Dry run | `--dry-run` | Planning only |

Gates and evidence levels are documented in [Running benchmarks](execution.md).

## Release gate pipeline

`pcs-bench gate` runs the following steps.

1. Materialize fixtures
2. Verify fixture manifest
3. Validate cases
4. Validate reference producer ingests
5. Benchmark with `--ci`
6. Optionally merge producer `PcsBenchIngest.v0` (`--run-producer-benchmarks`)
7. Validate report against `BenchmarkReport.v0`
8. Export packet
9. Verify packet (optional `--reproduce-smoke`)

Producer merge behavior is described in [Producer integration](producers.md).

## Evaluation pipelines

Workflow-specific stage lists live in `pipeline/registry.py`.

- **Release pipeline** — validate chain, runtime verify, certificates, admission, scientific-memory, Lean
- **Formal pipeline** — Lean obligations and check results
- **Memory pipeline** — import, render, staleness

Each stage records commands in `CaseExecutionContext` and may write `artifact_analysis.json` per case.

## Main modules

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Command-line interface |
| `producer_ingest.py` | Normalize `PcsBenchIngest.v0` to `BenchmarkReport.v0` |
| `producer_gate.py` | Producer benchmark orchestration and merge |
| `producer_doctor.py` | Producer readiness diagnostics |
| `ingest_validation.py` | Ingest schema and release-grade rules |
| `producer_artifacts.py` | Merge manifest and gate result files |
| `pipeline/` | Declarative evaluation stages |
| `artifacts.py` | Certificate, registry, rendering analysis |
| `simulation.py` | Expected outcomes for offline runs |
| `adapters/` | CLI wrappers |
| `cases.py` / `suites.py` | Load cases and suite manifests |
| `metrics.py` | Score computation |
| `reports.py` / `report_export.py` | Report persistence and pcs-core export shape |
| `packet.py` | Reviewer packet export and verification |
| `release_readiness.py` | One-shot release status |

## Adapter contract

Every external call goes through `RepoAdapter.run()`, which returns a `CommandResult` stored in the benchmark report. pcs-bench limits itself to public command-line interfaces and keeps sibling repository internals outside the harness boundary.

## Workspace layout

```
.pcs-bench-workspaces/run-<timestamp>/
  cases/case-<case_id>/
    input/
    output/
    logs/
    artifacts/
    command_history.json
```

Runs treat source repositories as read-only and leave producer trees unchanged.
