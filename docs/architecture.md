# Architecture

pcs-bench is an **evaluation harness** that orchestrates the PCS ecosystem from the outside. It does not own PCS schemas, certificates, workflows, admission logic, or rendering.

## Evidence chain under evaluation

```
runtime evidence
  -> certificate or witness
  -> certified claim bundle
  -> verifier admission
  -> signed science claim bundle
  -> formal trust-envelope check
  -> Scientific Memory import and rendering
```

## Execution modes

| Mode | Flag | Behavior |
|------|------|----------|
| Simulate | `--simulate` (default) | Fixture sidecars + artifact analysis; no CLIs required |
| Live | `--live` | Invokes pcs, labtrust, certifyedge, pf, just |
| Dry-run | `--dry-run` | Planning only; fastest |

## Pipeline

Workflow-specific stage lists live in `pipeline/registry.py`:

- **RELEASE_PIPELINE** — validate chain, runtime verify, CertifyEdge, PF admission/explain, Scientific Memory, Lean
- **FORMAL_PIPELINE** — Lean obligations and check results
- **MEMORY_PIPELINE** — import, render, staleness

Each stage records commands in `CaseExecutionContext` and writes `artifact_analysis.json` per case.

## Components

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Typer CLI: run, report, compare, validate-cases, explain, check-adapters, list-suites |
| `pipeline/` | Declarative evaluation stages |
| `artifacts.py` | Certificate, registry, and rendering completeness analysis |
| `simulation.py` | Expected sidecar loading for offline evaluation |
| `config.py` | `pcs-bench.yaml` loading and CLI overrides |
| `adapters/` | CLI wrappers for pcs-core, LabTrust, CertifyEdge, PF, Scientific Memory |
| `cases.py` / `suites.py` | Load `BenchmarkCase.v0` and suite manifests |
| `validation.py` | Structural validation + optional `pcs validate` |
| `runners.py` | Per-case execution paths and command recording |
| `metrics.py` | Score computation |
| `reports.py` | `BenchmarkReport.v0` JSON persistence |
| `report_renderers/` | Markdown, HTML, CSV, JSON human reports |
| `baselines.py` | Regression comparison |
| `workspace.py` | Isolated per-run and per-case workspaces |
| `ci.py` | Threshold enforcement |

## Adapter contract

Every external interaction goes through `RepoAdapter.run()`, which returns a `CommandResult` recorded in the benchmark report. pcs-bench never imports internals from sibling repos.

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

Source repos are never mutated during a run.
