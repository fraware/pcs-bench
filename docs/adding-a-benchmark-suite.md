# Adding a benchmark suite

Follow this checklist when adding a new suite under `benchmarks/`. Case definitions must use pcs-core `BenchmarkCase.v0` only, and parallel schemas inside pcs-bench are out of scope.

## Steps

1. Create `benchmarks/<suite_name>/suite.yaml` with `suite_id`, `workflow_id`, `domain`, `cases`, and metric policy (`required_metrics` / `optional_metrics`).
2. Add cases under `valid/` and `invalid/`, each with `benchmark_case.v0.json` and `input_artifacts/`.
3. Add `expected/verification_result.json` for simulate-mode evaluation, and add `rendered_sections.json` when testing scientific-memory rendering.
4. Register a CLI alias in `SUITE_ALIASES` in `src/pcs_bench/config.py` when you want a kebab-case name (for example `my-suite` maps to `my_suite`).
5. Extend `runners.py` with a workflow-specific execution path when the default LabTrust flow is insufficient for the new workflow.
6. Run `python scripts/materialize_fixtures.py` when sharing templates from `benchmarks/_templates/`.
7. Validate and dry-run.

```bash
pcs-bench validate-cases --suite <alias> --dry-run
pcs-bench run --suite <alias> --dry-run
pcs-bench run --suite <alias> --simulate --out reports/my-suite.json
```

8. Update the fixture manifest when inputs change.

```bash
pcs-bench verify-fixtures --write
```

9. Add or update `benchmarks/<suite_name>/README.md` describing cases and expected outcomes.

## Existing suite aliases

| CLI alias | Directory |
|-----------|-----------|
| `labtrust-qc-release` | `labtrust_qc_release` |
| `tool-use-safety` | `tool_use_safety` |
| `computation-reproducibility` | `computation_reproducibility` |
| `formal-trust-kernel` | `formal_trust_kernel` |
| `scientific-memory-rendering` | `scientific_memory_rendering` |
| `cross-domain` | `cross_domain` |

## Related documentation

- [Benchmark methodology](benchmark-methodology.md) for suite layout and principles
- [Metrics](metrics.md) for scoring and applicability
- [CONTRIBUTING.md](../CONTRIBUTING.md) for the pull request checklist
