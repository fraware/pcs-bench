# Architecture

pcs-bench is an evaluation harness that orchestrates the PCS ecosystem from the outside. It does not own PCS schemas, certificates, workflows, admission logic, or rendering.

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

## Execution modes

| Mode | Flag | Behavior |
|------|------|----------|
| Simulate | `--simulate` (default) | Expected outcome files + artifact analysis; no CLIs required |
| Live | `--live` | Invokes pcs-core, LabTrust, CertifyEdge, provability-fabric, scientific-memory CLIs |
| Hybrid | `--hybrid` | Live first; expected outcomes when CLIs exit 127 |
| Dry run | `--dry-run` | Planning only |

See [Running benchmarks](execution.md) for gates and evidence levels.

## Release gate pipeline

`pcs-bench gate` runs:

1. Materialize fixtures
2. Verify fixture manifest
3. Validate cases
4. Validate reference producer ingests
5. Benchmark with `--ci`
6. Optionally aggregate producer `PcsBenchIngest.v0` (`--run-producer-benchmarks`)
7. Validate report against `BenchmarkReport.v0`
8. Export packet
9. Verify packet (optional `--reproduce-smoke`)

With `--run-producer-benchmarks`, the gate merges four producer ingests with pcs-bench suites. See [Producer integration](producers.md).

## Pipeline stages

Workflow-specific stage lists live in `pipeline/registry.py`:

- **Release pipeline** — validate chain, runtime verify, CertifyEdge, admission, scientific-memory, Lean
- **Formal pipeline** — Lean obligations and check results
- **Memory pipeline** — import, render, staleness

Each stage records commands in `CaseExecutionContext` and writes `artifact_analysis.json` per case.

## Main modules

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Command-line interface |
| `producer_ingest.py` | `PcsBenchIngest.v0` to `BenchmarkReport.v0` normalization |
| `producer_gate.py` | Producer benchmark orchestration and gate aggregation |
| `producer_doctor.py` | Producer readiness diagnostics |
| `ingest_validation.py` | Ingest schema and release-grade validation |
| `pipeline/` | Declarative evaluation stages |
| `artifacts.py` | Certificate, registry, and rendering analysis |
| `simulation.py` | Expected outcome loading for offline evaluation |
| `adapters/` | CLI wrappers for ecosystem repositories |
| `cases.py` / `suites.py` | Load `BenchmarkCase.v0` and suite manifests |
| `metrics.py` | Score computation |
| `reports.py` | `BenchmarkReport.v0` persistence |
| `packet.py` | Reviewer packet export and verification |

## Adapter contract

Every external interaction goes through `RepoAdapter.run()`, which returns a `CommandResult` recorded in the benchmark report. pcs-bench never imports internals from sibling repositories.

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

Source repositories are never mutated during a run.
