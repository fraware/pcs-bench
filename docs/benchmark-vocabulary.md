# Benchmark vocabulary

pcs-bench and pcs-core use **two separate status fields** on every benchmark case. Do not mix harness results with PCS admission outcomes.

## Benchmark harness status

`expected_status` / `BenchmarkRun.observed_status` (schema: `benchmark_observed_status`):

| Value | Meaning |
|-------|---------|
| `passed` | Case expectation met (valid release admitted, or invalid release correctly rejected) |
| `failed` | Case expectation not met |
| `skipped` | Case not executed |
| `error` | Harness or adapter error |

## System outcome

`expected_system_outcome` / `BenchmarkRun.observed_system_outcome` (schema: `benchmark_system_outcome`):

| Value | Meaning |
|-------|---------|
| `admitted` | PCS admission path succeeded |
| `rejected` | Release or verification rejected |
| `stale` | Staleness detected |
| `import_failed` | Scientific Memory import failed |
| `render_failed` | Rendering incomplete or failed |
| `formal_failed` | Formal / Lean check failed |

Older fixtures that used `Admitted` / `Rejected` as `expected_status` are normalized at load time into the split above.

## BenchmarkReport metrics

Exported `BenchmarkReport.v0` JSON uses:

- `metrics`: array of metric **names** (for example `release_reproducibility_score`)
- `metric_summaries`: scored entries with `name`, `score`, `applicability`, optional `reason`, `numerator`, `denominator`

## Evidence grade

| Field | Values |
|-------|--------|
| `summary.execution_mode` | `live`, `simulate`, `hybrid`, `dry_run` |
| `summary.evidence_grade` | `release` (CI + live only) or `developer` (simulate/hybrid) |

Release-grade reports require `execution_mode=live`, `live_cases > 0`, and no `hybrid_fallback_cases` for suites marked `live_required_for_release: true` in `suite.yaml`.
