# Benchmark Methodology

## Principles

1. **External evaluation** — pcs-bench calls public CLIs only.
2. **Schema authority in pcs-core** — cases use `BenchmarkCase.v0`; reports use `BenchmarkReport.v0`.
3. **Isolated workspaces** — each case runs in its own directory under `.pcs-bench-workspaces/`.
4. **Full command audit** — every subprocess is recorded with exit code, duration, and streams.

## Suite structure

Each suite under `benchmarks/<name>/` contains:

- `suite.yaml` — suite metadata and case references
- `valid/` and `invalid/` — case directories with `benchmark_case.v0.json` and `input_artifacts/`
- `README.md` — suite-specific documentation

## LabTrust QC release path (MVP)

For `hospital_lab.qc_release` cases:

1. `pcs validate-release-chain <release_dir>`
2. `labtrust verify-release-protocol --release-dir <dir>`
3. `pf verify release-chain` / `pf verify science-claim` when artifacts exist
4. Scientific Memory `pcs-import-release` when manifest exists

## Dry-run mode

`pcs-bench run --dry-run` plans execution and produces a report without invoking external binaries. Use for CI scaffolding and local development without sibling repos installed.
