# Metrics

pcs-bench computes eight core metrics aligned with pcs-core benchmark schemas. Each metric carries an applicability state so scores reflect only the dimensions a suite actually exercises.

## Applicability states

| State | Meaning |
|-------|---------|
| `measured` | Score computed from cases in this run; subject to CI thresholds |
| `not_applicable` | Suite declares the metric optional and no cases apply |
| `insufficient_cases` | No relevant cases in this run (score is `null`) |
| `skipped` | Explicitly skipped (reserved) |
| `failed_to_measure` | Suite requires the metric yet the run includes no measurable cases (CI fails) |

Exported `BenchmarkReport.v0` JSON lists metric names and structured summaries.

```json
{
  "metrics": [
    "release_reproducibility_score",
    "formal_check_coverage_score"
  ],
  "metric_summaries": [
    {
      "name": "release_reproducibility_score",
      "score": 0.95,
      "applicability": "measured",
      "numerator": 19,
      "denominator": 20
    },
    {
      "name": "formal_check_coverage_score",
      "score": null,
      "applicability": "insufficient_cases",
      "reason": "No formal-check cases were present in this suite."
    }
  ]
}
```

The [Benchmark vocabulary](benchmark-vocabulary.md) explains how harness status differs from system outcome.

## Core metrics

| Metric | Definition |
|--------|------------|
| `release_reproducibility_score` | Valid cases that pass release-chain validation and hash checks |
| `failure_localization_accuracy` | Invalid cases where observed responsible component matches expected |
| `certificate_completeness_score` | Certificates/witnesses contain required fields |
| `registry_coverage_score` | Release artifacts registered and checked |
| `formal_check_coverage_score` | Required formal obligations Lean-checked |
| `scientific_memory_interpretability_score` | Rendered output contains required evidence sections |
| `repair_hint_quality_score` | Rejected cases include actionable repair guidance |
| `cross_domain_portability_score` | Shared PCS protocol path across workflow domains |

## Suite policy

Each `suite.yaml` may declare required and optional metrics.

```yaml
required_metrics:
  - failure_localization_accuracy
  - repair_hint_quality_score
optional_metrics:
  - formal_check_coverage_score
```

`pcs-bench run --suite all` expects all eight core metrics to be **measured** or explicitly optional per suite policy.

Thresholds are configured in `pcs-bench.yaml` and enforced in `--ci` mode for **measured** metrics only. See [Configuration](configuration.md).
