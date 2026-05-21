# Windows-friendly Make targets (use when GNU make is awkward with PATH)
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$PcsBench = "$Python -m pcs_bench"

function Run($cmd) {
    Write-Host ">> $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "install" { Run "$Python -m pip install -e `".[dev]`"" }
    "fixtures" { Run "$Python scripts/materialize_fixtures.py" }
    "manifest" {
        Run "$Python scripts/materialize_fixtures.py"
        Run "$PcsBench verify-fixtures --write"
        Run "$PcsBench verify-fixtures"
    }
    "schemas" { Run "$Python scripts/sync_pcs_core_schema.py --pcs-core ../pcs-core" }
    "test" { Run "$Python -m pytest -q" }
    "bench" { Run "$PcsBench run --suite all --simulate --out reports/latest.json" }
    "ci" {
        & $PSScriptRoot/make.ps1 gate
        Run "$PcsBench report --input reports/ci.json --format markdown --out reports/ci.md"
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    "sync-ingest-fixtures" {
        Run "$Python scripts/sync_pcs_core_ingest_fixtures.py --pcs-core ../pcs-core"
    }
    "validate-producer-ingest" {
        Run "$Python scripts/validate_producer_ingest_fixtures.py --pcs-core ../pcs-core"
    }
    "check-producer-ingests" {
        Run "$PcsBench check-producer-ingests --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "check-producer-ingest-fixtures" {
        Run "$PcsBench check-producer-ingests --fixtures-only --pcs-core ../pcs-core"
    }
    "producer-gate" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --suite all --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke --out reports/producer-gate.json --out-packet packets/producer-gate --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "producer-gate-live" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --suite all --live --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke --out reports/producer-gate.json --out-packet packets/producer-gate --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "gate" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --out reports/ci.json --out-packet packets/latest --reproduce-smoke"
    }
    "packet" {
        & $PSScriptRoot/make.ps1 ci
    }
    "html" {
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    default {
        Write-Host @"
Targets: install, fixtures, manifest, schemas, test, bench, ci, gate, producer-gate, check-producer-ingests, sync-ingest-fixtures, packet, html
Example: .\make.ps1 gate
"@
    }
}
