# Use python -m pcs_bench so targets work when the console script is not on PATH (common on Windows).
PYTHON ?= python
PCS_BENCH = $(PYTHON) -m pcs_bench

.PHONY: install test bench ci gate fixtures manifest packet schemas lint clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

fixtures:
	$(PYTHON) scripts/materialize_fixtures.py

manifest: fixtures
	$(PCS_BENCH) verify-fixtures --write
	$(PCS_BENCH) verify-fixtures

schemas:
	$(PYTHON) scripts/sync_pcs_core_schema.py --pcs-core ../pcs-core

test:
	$(PYTHON) -m pytest -q

bench:
	$(PCS_BENCH) run --suite all --simulate --out reports/latest.json

ci: gate
	$(PCS_BENCH) report --input reports/ci.json --format markdown --out reports/ci.md
	$(PCS_BENCH) report --input reports/ci.json --format html --out reports/ci.html

gate: install
	$(PCS_BENCH) gate --out reports/ci.json --out-packet packets/latest

packet: ci
	$(PCS_BENCH) packet --report reports/ci.json --out packets/latest
	$(PCS_BENCH) verify-packet --packet packets/latest

lint:
	$(PYTHON) -m ruff check src tests

clean:
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('.pytest_cache')]"
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]"
	-$(PYTHON) -c "import shutil; shutil.rmtree('dist', ignore_errors=True); shutil.rmtree('build', ignore_errors=True)"
