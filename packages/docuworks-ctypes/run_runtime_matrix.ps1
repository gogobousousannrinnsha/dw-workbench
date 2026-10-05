[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$BlankFixture,
    [Parameter(Mandatory = $true)] [string]$Sdk10Dll,
    [Parameter(Mandatory = $true)] [string]$Sdk917Dll,
    [string]$ArtifactRoot
)

$ErrorActionPreference = "Stop"
$fixture = (Resolve-Path -LiteralPath $BlankFixture).Path
$sdk10 = (Resolve-Path -LiteralPath $Sdk10Dll).Path
$sdk917 = (Resolve-Path -LiteralPath $Sdk917Dll).Path
if (-not $ArtifactRoot) {
    $ArtifactRoot = Join-Path $PSScriptRoot ("runtime-matrix-runs\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$root = [System.IO.Path]::GetFullPath($ArtifactRoot)
if (Test-Path -LiteralPath $root) {
    if (Get-ChildItem -LiteralPath $root -Force | Select-Object -First 1) {
        throw "ArtifactRoot must be empty or new: $root"
    }
} else {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
}
$before = (Get-FileHash -Algorithm SHA256 -LiteralPath $fixture).Hash
$report = Join-Path $root "runtime-resolution.json"
& py -3.11 (Join-Path $PSScriptRoot "generate_runtime_report.py") `
    --verification-document $fixture `
    --search-path (Split-Path -Parent $sdk10) `
    --search-path (Split-Path -Parent $sdk917) `
    --output $report 2>&1 | Tee-Object -FilePath (Join-Path $root "runtime-resolution.log")
if ($LASTEXITCODE -ne 0) { throw "runtime report failed" }

$smokeResult = Join-Path $root "sdk10-simple-smoke.json"
$smokeXdw = Join-Path $root "sdk10-simple-smoke.xdw"
& py -3.11 (Join-Path $PSScriptRoot "compatibility_smoke.py") `
    --fixture $fixture --output-xdw $smokeXdw --result $smokeResult --dll-path $sdk10
if ($LASTEXITCODE -ne 0) { throw "SDK 10.0 Simple smoke failed" }

& py -3.11 (Join-Path $PSScriptRoot "verify_runtime_matrix.py") `
    --report $report --sdk10-dll $sdk10 --sdk917-dll $sdk917 `
    --sdk10-smoke $smokeResult --output (Join-Path $root "runtime-matrix.json")
if ($LASTEXITCODE -ne 0) { throw "runtime matrix verification failed" }
$after = (Get-FileHash -Algorithm SHA256 -LiteralPath $fixture).Hash
if ($after -ne $before) { throw "Blank fixture was modified" }
Write-Host "Runtime matrix verified: $root"
