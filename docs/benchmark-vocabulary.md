# Benchmark vocabulary

pcs-bench and pcs-core use **two separate status fields** on every benchmark case, and readers should keep harness results separate from PCS admission outcomes.

## Benchmark harness status

`expected_status` and `BenchmarkRun.observed_status` use schema type `benchmark_observed_status`.

| Value | Meaning |
|-------|---------|
| `passed` | Case expectation met (valid release admitted, or invalid release correctly rejected) |
| `failed` | Case expectation unmet |
| `skipped` | Case omitted from execution |
| `error` | Harness or adapter error |

## System outcome

`expected_system_outcome` and `BenchmarkRun.observed_system_outcome` use schema type `benchmark_system_outcome`.

| Value | Meaning |
|-------|---------|
| `admitted` | PCS admission path succeeded |
| `rejected` | Release or verification rejected |
| `stale` | Staleness detected |
| `import_failed` | Scientific Memory import failed |
| `render_failed` | Rendering incomplete or failed |
| `formal_failed` | Formal / Lean check failed |

Older fixtures that stored `Admitted` or `Rejected` inside `expected_status` are normalized at load time into the split fields above.

## BenchmarkReport metrics

Exported `BenchmarkReport.v0` JSON uses two parallel structures.

- `metrics` holds an array of metric names such as `release_reproducibility_score`
- `metric_summaries` holds scored entries with `name`, `score`, `applicability`, optional `reason`, `numerator`, and `denominator`

## Evidence grade

| Field | Values |
|-------|--------|
| `summary.execution_mode` | `live`, `simulate`, `hybrid`, `dry_run` |
| `summary.evidence_grade` | `release` (CI + live) or `developer` (simulate/hybrid) |

Release-grade reports need `execution_mode=live`, `live_cases > 0`, and zero `hybrid_fallback_cases` for suites marked `live_required_for_release: true` in `suite.yaml`. See [Running benchmarks](execution.md) and [Release guide](release.md).
