# Benchmark methodology

## Principles

1. **External evaluation** — pcs-bench calls public command-line interfaces only and keeps sibling repository code outside the harness boundary.
2. **Schema authority in pcs-core** — cases use `BenchmarkCase.v0` and reports use `BenchmarkReport.v0`.
3. **Isolated workspaces** — each case runs under `.pcs-bench-workspaces/run-<timestamp>/cases/case-<case_id>/`.
4. **Full command audit** — every subprocess is recorded with exit code, duration, and streams.

## Suite catalog

| Suite | Workflow domain | Cases (approx.) |
|-------|-----------------|-----------------|
| `labtrust_qc_release` | Hospital lab QC release | 9 |
| `tool_use_safety` | Tool-use certificates | 10 |
| `computation_reproducibility` | Computation witnesses | 10 |
| `formal_trust_kernel` | Lean obligations | 2 |
| `scientific_memory_rendering` | Evidence rendering | 8 |
| `cross_domain` | Shared PCS protocol | 3 |

CLI aliases such as `labtrust-qc-release` are listed in [Adding a benchmark suite](adding-a-benchmark-suite.md).

## Suite layout

Each suite under `benchmarks/<name>/` contains the following pieces.

- `suite.yaml` for metadata, case list, and metric policy
- `valid/` and `invalid/` directories for cases
- `benchmark_case.v0.json` and `input_artifacts/` per case
- `expected/verification_result.json` for offline evaluation
- `README.md` (recommended) as a case matrix for reviewers

## LabTrust QC release evaluation path

For `hospital_lab.qc_release` cases, the harness typically invokes the following tools in order.

1. `pcs validate-release-chain <release_dir>`
2. `labtrust verify-release-protocol --release-dir <dir>`
3. `pf verify release-chain` or `pf verify science-claim` when artifacts exist
4. Scientific Memory import when a manifest exists

Per-case detail appears in [benchmarks/labtrust_qc_release/README.md](../benchmarks/labtrust_qc_release/README.md).

## Dry-run mode

```bash
pcs-bench run --suite <alias> --dry-run
```

Dry-run mode plans execution and produces a report skeleton while skipping external binaries, which helps contributors who have only pcs-bench checked out locally.
