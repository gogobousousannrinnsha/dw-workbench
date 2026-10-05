[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BlankFixture,

    [Parameter(Mandatory = $true)]
    [string]$DateStampFixture,

    [string]$DllPath,
    [int]$CodePage = 0,
    [string]$ArtifactRoot
)

$ErrorActionPreference = "Stop"

$blank = (Resolve-Path -LiteralPath $BlankFixture).Path
$dateStamp = (Resolve-Path -LiteralPath $DateStampFixture).Path
if (-not $ArtifactRoot) {
    $runId = Get-Date -Format "yyyyMMdd-HHmmss"
    $ArtifactRoot = Join-Path $PSScriptRoot "integration-artifacts\$runId"
}
$artifacts = [System.IO.Path]::GetFullPath($ArtifactRoot)
if (Test-Path -LiteralPath $artifacts) {
    if (Get-ChildItem -LiteralPath $artifacts -Force | Select-Object -First 1) {
        throw "ArtifactRoot must be empty or new: $artifacts"
    }
} else {
    New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
}

$env:DOCUWORKS_TEST_XDW = $blank
$env:DOCUWORKS_DATE_STAMP_XDW = $dateStamp
$env:DOCUWORKS_ARTIFACT_ROOT = $artifacts
if ($DllPath) {
    $env:DOCUWORKS_DLL = (Resolve-Path -LiteralPath $DllPath).Path
} else {
    Remove-Item Env:DOCUWORKS_DLL -ErrorAction SilentlyContinue
}
if ($CodePage -gt 0) {
    $env:DOCUWORKS_CODEPAGE = [string]$CodePage
} else {
    Remove-Item Env:DOCUWORKS_CODEPAGE -ErrorAction SilentlyContinue
}

$fixtureManifest = [ordered]@{
    run_started = (Get-Date).ToString("o")
    blank_fixture = $blank
    blank_fixture_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $blank).Hash
    date_stamp_fixture = $dateStamp
    date_stamp_fixture_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $dateStamp).Hash
    requested_dll = $env:DOCUWORKS_DLL
    requested_search_paths = $env:DOCUWORKS_XDWAPI_PATHS
    requested_codepage = $env:DOCUWORKS_CODEPAGE
    artifact_root = $artifacts
}
$fixtureManifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $artifacts "run-manifest.json")

$viewerTemplate = [ordered]@{
    schema_version = 2
    verified_at = $null
    verified_by = ""
    artifact_scope = $artifacts
    items = [ordered]@{
        annotation_display = [ordered]@{ verified = $false; notes = "" }
        text_rendering = [ordered]@{ verified = $false; notes = "" }
        no_corruption_warning = [ordered]@{ verified = $false; notes = "" }
        annotation_reeditable = [ordered]@{ verified = $false; notes = "" }
        ascii_document_format_unchanged = [ordered]@{ verified = $false; notes = "" }
    }
    annotation_types = [ordered]@{
        TEXT = [ordered]@{ verified = $false; notes = "" }
        LINK = [ordered]@{ verified = $false; notes = "" }
        STICKY = [ordered]@{ verified = $false; notes = "" }
        STRAIGHT_LINE = [ordered]@{ verified = $false; notes = "" }
        RECTANGLE = [ordered]@{ verified = $false; notes = "" }
        ELLIPSE = [ordered]@{ verified = $false; notes = "" }
        DATE_STAMP = [ordered]@{ verified = $false; notes = "" }
        MARKER = [ordered]@{ verified = $false; notes = "" }
        POLYGON = [ordered]@{ verified = $false; notes = "" }
    }
}
$viewerTemplate | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $artifacts "viewer-verification.json")

$runtimeReport = Join-Path $artifacts "runtime-resolution.json"
$runtimeReportConsole = Join-Path $artifacts "runtime-report-console.log"
$runtimeReportScript = Join-Path $PSScriptRoot "generate_runtime_report.py"
$runtimeArguments = @(
    $runtimeReportScript,
    "--verification-document", $blank,
    "--output", $runtimeReport
)
if ($DllPath) {
    $runtimeArguments += @("--dll-path", $env:DOCUWORKS_DLL)
} elseif (-not [string]::IsNullOrWhiteSpace($env:DOCUWORKS_XDWAPI_PATHS)) {
    foreach ($searchPath in $env:DOCUWORKS_XDWAPI_PATHS.Split([System.IO.Path]::PathSeparator)) {
        if (-not [string]::IsNullOrWhiteSpace($searchPath)) {
            $runtimeArguments += @("--search-path", $searchPath)
        }
    }
}
& py @runtimeArguments 2>&1 | Tee-Object -FilePath $runtimeReportConsole
$runtimeReportExitCode = $LASTEXITCODE

$contractJunit = Join-Path $artifacts "contract-junit.xml"
$contractConsole = Join-Path $artifacts "contract-console.log"
$pytestConfig = Join-Path $PSScriptRoot "pyproject.toml"
$testsPath = Join-Path $PSScriptRoot "tests"
& py -m pytest -c $pytestConfig $testsPath -ra -m "not integration" --junitxml=$contractJunit 2>&1 | Tee-Object -FilePath $contractConsole
$contractExitCode = $LASTEXITCODE

$junit = Join-Path $artifacts "integration-junit.xml"
$console = Join-Path $artifacts "integration-console.log"
& py -m pytest -c $pytestConfig $testsPath -ra -m integration --junitxml=$junit 2>&1 | Tee-Object -FilePath $console
$integrationExitCode = $LASTEXITCODE

$coveragePath = Join-Path $artifacts "standard-coverage.json"
$coverageGenerator = Join-Path $PSScriptRoot "generate_standard_coverage.py"
& py $coverageGenerator --evidence (Join-Path $artifacts "evidence.jsonl") --output $coveragePath
$coverageExitCode = $LASTEXITCODE
$coverage = Get-Content -Raw -LiteralPath $coveragePath | ConvertFrom-Json

[xml]$integrationXml = Get-Content -Raw -LiteralPath $junit
$testSummary = $integrationXml.testsuites.testsuite
$skipped = [int]$testSummary.skipped
$failed = [int]$testSummary.failures + [int]$testSummary.errors
$contractVerified = ($contractExitCode -eq 0)
$persistenceVerified = ($integrationExitCode -eq 0 -and $failed -eq 0 -and $skipped -eq 0)
$fullPersistenceVerified = ($persistenceVerified -and $coverageExitCode -eq 0 -and [bool]$coverage.full_persistence_verified)

$result = [ordered]@{
    run_finished = (Get-Date).ToString("o")
    contract_pytest_exit_code = $contractExitCode
    integration_pytest_exit_code = $integrationExitCode
    integration_failed = $failed
    integration_skipped = $skipped
    runtime_report_exit_code = $runtimeReportExitCode
    coverage_exit_code = $coverageExitCode
    standard_registry_count = [int]$coverage.registry_count
    standard_coverage_complete = [int]$coverage.complete_count
    contract_verified = $contractVerified
    persistence_verified = $persistenceVerified
    persistence_scope = $(if ($fullPersistenceVerified) { "XDWAPI_10_1_1_FULL_STANDARD_REGISTRY" } else { "REPRESENTATIVE_INTEGRATION_SUITE" })
    representative_persistence_verified = $persistenceVerified
    full_persistence_verified = $fullPersistenceVerified
    viewer_visual_edit_verified = $false
    viewer_format_verified = $false
    viewer_verified = $false
    viewer_verification = "PENDING_JOINT_REVIEW"
}
$result | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $artifacts "verification-status.json")

$finalizer = Join-Path $PSScriptRoot "finalize_evidence.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $finalizer -RunDirectory $artifacts
$evidencePackExitCode = $LASTEXITCODE

Write-Host "Artifacts: $artifacts"
if ($runtimeReportExitCode -ne 0) {
    exit $runtimeReportExitCode
}
if ($evidencePackExitCode -ne 0) {
    exit $evidencePackExitCode
}
if ($contractExitCode -ne 0) {
    exit $contractExitCode
}
if ($integrationExitCode -ne 0) {
    exit $integrationExitCode
}
if ($coverageExitCode -ne 0) {
    exit $coverageExitCode
}
if (-not $persistenceVerified) {
    Write-Warning "Integration run is incomplete because one or more cases were skipped."
    exit 3
}
exit 0
