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
    "gate" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --out reports/ci.json --out-packet packets/latest"
    }
    "packet" {
        & $PSScriptRoot/make.ps1 ci
    }
    "html" {
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    default {
        Write-Host @"
Targets: install, fixtures, manifest, schemas, test, bench, ci, gate, packet, html
Example: .\make.ps1 gate
"@
    }
}
