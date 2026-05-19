# Contributing to pcs-bench

## Development setup

```bash
pip install -e ".[dev]"
python scripts/materialize_fixtures.py
make test
```

## Adding benchmark cases

1. Add case under `benchmarks/<suite>/` with `benchmark_case.v0.json` and `input_artifacts/`.
2. Add `expected/verification_result.json` for simulate-mode evaluation.
3. Register in `suite.yaml`.
4. Run `pcs-bench validate-cases --suite <alias>`.
5. Update fixture manifest: `pcs-bench verify-fixtures --write`.

## Pull request checklist

- [ ] `pytest` passes
- [ ] `pcs-bench run --suite all --simulate --ci` passes
- [ ] No PCS schemas redefined in this repo
- [ ] Case manifests validate against embedded or pcs-core JSON Schema

## Commit style

Use clear, sentence-style messages focused on why the change matters for PCS evaluation.
