# Changelog

## 0.3.0 (2026-05-22)

- `make release-prep` / `make release-verify` for one-command offline prep and post-live-ci verification
- Fix producer gate report validation: harness-only fields moved to `producer_gate_result.v0.json` (not `BenchmarkReport.v0` summary)
- Gate success output lists smoke report and `producer_gate_result.v0.json` when present
- Public documentation set: `docs/release.md`, `docs/producers.md`, `docs/execution.md`, `docs/configuration.md`
- Producer contract matrix (`producer_contracts.py`, documented in `docs/producers.md`)
- `pcs-bench producer-doctor`, `check-producer-ingests`, `validate-ingest --release-grade`
- Producer gate aggregation with `producer_merge_manifest.v0.json` and `producer_gate_result.v0.json`
- Canonical ingest reuse for release-grade gates; `--refresh-producer-ingests`
- `make live-ci` / `make release-check` for full live release evidence
- `pcs-bench release-readiness` one-shot status command
- Packet `verify-packet --reproduce-smoke` writes `packet_reproduction_report.v0.json`
- Fixture fallback marks `evidence_grade: developer` on aggregate reports

## 0.2.0

- Full LabTrust QC case matrix (9 cases) aligned with PCS benchmark spec
- Six benchmark suites, 20 cases, simulate/hybrid/live execution modes
- Declarative evaluation pipeline with artifact analysis and coverage metrics
- Benchmark packet export for external reviewers
- Embedded JSON Schema for offline case/report validation
- Fixture integrity manifest (`verify-fixtures`)
- Professional HTML reports with threshold highlighting
- Parallel case execution in simulate mode
- Failure localization parsing (`FailureLocalizationResult.v0` shape)
- Computation witness fixtures for reproducibility suite

## 0.1.0

- Initial pcs-bench harness: CLI, adapters, LabTrust MVP suite, metrics, CI
