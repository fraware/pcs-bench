# Contributing to pcs-bench

Thank you for helping improve the PCS evaluation harness. This project measures Proof-Carrying Science releases, and protocol definitions remain in [pcs-core](https://github.com/SentinelOps-CI/pcs-core) where they belong.

## Development setup

```bash
git clone https://github.com/fraware/pcs-bench.git
cd pcs-bench
pip install -e ".[dev]"
python scripts/materialize_fixtures.py
pcs-bench init
```

## Before opening a pull request

```bash
make release-prep
```

That target runs lint, schema sync, release-grade fixture validation, pytest, the standard offline gate, and the producer offline gate, and it completes with only this repository checked out.

When you change CLI or gate behavior, update [docs/execution.md](docs/execution.md), [docs/producers.md](docs/producers.md), or [docs/release.md](docs/release.md). The documentation index is [docs/README.md](docs/README.md).

## Adding benchmark cases

1. Add a case under `benchmarks/<suite>/` with `benchmark_case.v0.json` and `input_artifacts/`.
2. Add `expected/verification_result.json` for simulate-mode evaluation.
3. Register the case in `suite.yaml`.
4. Run `pcs-bench validate-cases --suite <alias>`.
5. Update the fixture manifest with `pcs-bench verify-fixtures --write`.

See [Adding a benchmark suite](docs/adding-a-benchmark-suite.md).

## Pull request checklist

- [ ] `make release-prep` passes (or `.\make.ps1 release-prep` on Windows)
- [ ] PCS schemas stay defined only in pcs-core
- [ ] Case manifests validate against pcs-core or embedded JSON Schema
- [ ] Documentation reflects any user-visible behavior change

## Live release verification (maintainers)

When all producer repositories are available locally, run the live path.

```bash
make live-ci
make release-verify
```

See [Release guide](docs/release.md).

## Commit messages

Use clear, sentence-style messages that explain why the change matters for PCS evaluation.

## License

By contributing, you agree that your contributions are licensed under the Apache-2.0 license in [LICENSE](LICENSE).
