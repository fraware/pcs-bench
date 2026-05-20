# Metrics

pcs-bench computes eight core metrics aligned with pcs-core benchmark schemas. Each metric has an **applicability** state so simulation cannot inflate scores for dimensions the suite does not exercise.

## Applicability states

| State | Meaning |
|-------|---------|
| `measured` | Score computed from cases in this run; subject to CI thresholds |
| `not_applicable` | Suite declares the metric optional and no cases apply |
| `insufficient_cases` | No relevant cases in this run (score is `null`) |
| `skipped` | Explicitly skipped (reserved) |
| `failed_to_measure` | Suite **requires** the metric but no cases could measure it (CI fails) |

Exported `BenchmarkReport.v0` JSON uses numeric scores only for `measured` metrics. Other states appear as structured objects:

```json
{
  "formal_check_coverage_score": {
    "score": null,
    "applicability": "insufficient_cases",
    "reason": "No formal-check cases were present in this suite."
  }
}
```

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

Each `suite.yaml` may declare:

```yaml
required_metrics:
  - failure_localization_accuracy
  - repair_hint_quality_score
optional_metrics:
  - formal_check_coverage_score
```

`pcs-bench run --suite all` requires all eight core metrics to be **measured** or explicitly optional per suite policy.

Thresholds are configured in `pcs-bench.yaml` and enforced in `--ci` mode for **measured** metrics only.
