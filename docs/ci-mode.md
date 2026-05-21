# CI mode

Run the full evaluation gate:

```bash
make ci
# or
pcs-bench run --suite all --simulate --ci --out reports/ci.json
pcs-bench validate-report --input reports/ci.json
pcs-bench packet --report reports/ci.json --out packets/latest
pcs-bench verify-packet --packet packets/latest --reproduce-smoke
pcs-bench validate-producer-fixtures --pcs-core ../pcs-core
```

One-shot local gate:

```bash
pcs-bench gate --reproduce-smoke
```

## Failure conditions

CI mode exits non-zero when:

- A valid release is rejected (`valid_release_rejected`)
- An invalid release is not detected (`invalid_release_not_detected`)
- Any **measured** metric score falls below its threshold in `pcs-bench.yaml`
- A **required** metric could not be measured (`failed_to_measure`)
- The emitted report fails `BenchmarkReport.v0` validation
- A live-required suite ran with `live_cases == 0` while `--live` was not used
- A required suite directory is missing

Optional metrics with `insufficient_cases` do not fail CI unless listed under `required_metrics` for that suite.

## Output format

```
FAILED: failure_localization_accuracy below threshold
score: 0.82
threshold: 0.90
failed cases:
- labtrust-trace-hash-tamper-v0
```

```
FAILED: Required metric formal_check_coverage_score was not measured (insufficient_cases: No formal-check cases were present in this suite.)
```

## Recommended pipeline

1. `python scripts/materialize_fixtures.py`
2. `pcs-bench verify-fixtures --write` then commit `benchmarks/fixture_manifest.json`
3. `pcs-bench validate-cases --suite all --dry-run`
4. `pcs-bench run --suite all --simulate --ci --out reports/ci.json`
5. `pcs-bench validate-report --input reports/ci.json`
6. `pcs-bench report --input reports/ci.json --format markdown --out reports/ci.md`
7. `pcs-bench packet --report reports/ci.json --out packets/latest`
8. `pcs-bench verify-packet --packet packets/latest --reproduce-smoke`
9. `pcs-bench validate-producer-fixtures` (or rely on `gate`, which runs this step)
10. Optionally `pcs-bench compare --old reports/baseline.json --new reports/ci.json`

See [Live release gate](live-gate.md) for `--live --ci` on LabTrust.
