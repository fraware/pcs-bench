# Metrics

pcs-bench computes eight core metrics aligned with pcs-core benchmark schemas.

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

Thresholds are configured in `pcs-bench.yaml` and enforced in `--ci` mode.
