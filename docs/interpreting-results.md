# Interpreting results

## BenchmarkReport JSON

The machine-readable report (`BenchmarkReport.v0`) is the source of truth for automation and regression tracking. Each entry in `runs[]` records expected and observed harness status, expected and observed system outcome, failure codes, responsible components, commands executed, and artifact paths.

Validate a report with the following command.

```bash
pcs-bench validate-report --input reports/ci.json --pcs-core ../pcs-core
```

The [Benchmark vocabulary](benchmark-vocabulary.md) explains how harness status differs from system outcome.

## Human-readable reports

```bash
pcs-bench report --input reports/latest.json --format markdown --out reports/latest.md
pcs-bench report --input reports/latest.json --format html --out reports/latest.html
```

Typical sections include an executive summary with pass and fail counts, a failure localization matrix that shows whether invalid cases failed at the expected layer, a metric summary that compares scores to thresholds in `pcs-bench.yaml`, and an appendix with per-case detail for failures.

## Explaining a failure

```bash
pcs-bench explain --report reports/latest.json --case <case_id>
```

The command surfaces the first failing command, the responsible repository, a repair hint, and paths to logs or artifacts.

## Baseline comparison

```bash
pcs-bench compare --old reports/baseline.json --new reports/latest.json
pcs-bench compare --old reports/baseline.json --new reports/latest.json --format json
```

Review metric regressions, newly failing cases, and shifts in responsible components when you compare baselines.

## Reviewer packets

```bash
pcs-bench packet --report reports/ci.json --out packets/latest
pcs-bench verify-packet --packet packets/latest --reproduce-smoke
```

A packet usually contains the items below.

| Item | Purpose |
|------|---------|
| `BenchmarkReport.v0.json` | Aggregate results |
| `case_manifest.json` | Case list and fixture paths |
| Case fixture trees | Inputs for reproduction |
| `producer_merge_manifest.v0.json` | Present when producer gate ran |
| `producer_ingests/` | Copy of each producer ingest when merged |
| `packet_reproduction_report.v0.json` | Smoke-check results when `--reproduce-smoke` was used |

## Producer gate sidecar files

Producer gates may write companion files beside the aggregate report.

| File | Purpose |
|------|---------|
| `producer_gate_result.v0.json` | Pass or fail, errors, `use_fixture_fallback`, producer counts |
| `producer_merge_manifest.v0.json` | Provenance for each merged ingest |

These files sit outside `BenchmarkReport.v0` and document how the aggregate report was produced.
