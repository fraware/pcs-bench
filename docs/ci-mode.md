# CI Mode

Run the full evaluation gate:

```bash
pcs-bench run --suite labtrust-qc-release --ci --out reports/ci.json
```

## Failure conditions

CI mode exits non-zero when:

- A valid release is rejected
- An invalid release is accepted
- Any metric score falls below its threshold in `pcs-bench.yaml`
- A required suite directory is missing
- Case validation fails (when run via `validate-cases` in pipeline)

## Output format

```
FAILED: failure_localization_accuracy below threshold
score: 0.82
threshold: 0.90
failed cases:
- labtrust-trace-hash-tamper-v0
```

## Recommended pipeline

1. Install pcs-bench and sibling repo CLIs
2. `pcs-bench validate-cases --suite all`
3. `pcs-bench run --suite all --ci --out reports/ci.json`
4. `pcs-bench report --input reports/ci.json --format markdown --out reports/ci.md`
5. Upload `reports/ci.json` and `reports/ci.md` as artifacts
6. Optionally `pcs-bench compare --old reports/baseline.json --new reports/ci.json`
