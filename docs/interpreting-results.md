# Interpreting Results

## BenchmarkReport JSON

The machine-readable report (`BenchmarkReport.v0`) is the source of truth. Each `runs[]` entry records expected vs observed status, failure codes, responsible components, commands, and artifact paths.

## Human reports

Generate with:

```bash
pcs-bench report --input reports/latest.json --format markdown --out reports/latest.md
```

Key sections:

- **Executive summary** — pass/fail counts and timing
- **Failure localization matrix** — whether invalid cases failed at the expected layer
- **Metric summary** — scores vs thresholds in `pcs-bench.yaml`
- **Appendix** — per-case detail for failures

## Explaining a failure

```bash
pcs-bench explain --report reports/latest.json --case <case_id>
```

Shows first failing command, responsible repo, repair hint, and log/artifact paths.

## Baseline comparison

```bash
pcs-bench compare --old reports/baseline.json --new reports/latest.json
```

Look for metric regressions, new failing cases, and changed responsible components.
