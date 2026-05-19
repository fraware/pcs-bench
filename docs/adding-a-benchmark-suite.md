# Adding a Benchmark Suite

1. Create `benchmarks/<suite_name>/suite.yaml` with `suite_id`, `workflow_id`, `domain`, `cases`, and `metrics`.
2. Add cases as `benchmark_case.v0.json` files conforming to pcs-core `BenchmarkCase.v0`.
3. Place input fixtures under each case's `input_artifacts/` directory.
4. Register the suite alias in `config.py` `SUITE_ALIASES` if using a kebab-case CLI name.
5. Extend `runners.py` with a workflow-specific execution path if the default LabTrust path does not apply.
6. Validate: `pcs-bench validate-cases --suite <alias>`
7. Run: `pcs-bench run --suite <alias> --dry-run` then without `--dry-run` when sibling repos are available.

Do not define parallel case schemas in pcs-bench. Consume pcs-core definitions only.
