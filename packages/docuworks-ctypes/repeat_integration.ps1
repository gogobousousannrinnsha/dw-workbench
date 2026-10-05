[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "integration-test.config.json"
}

function Resolve-ConfiguredPath {
    param(
        [string]$Value,
        [string]$BaseDirectory,
        [string]$Label,
        [switch]$AllowMissing
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        if ($AllowMissing) {
            return $null
        }
        throw "$Label is not configured. Edit integration-test.config.json first."
    }
    if ([System.IO.Path]::IsPathRooted($Value)) {
        $candidate = $Value
    } else {
        $candidate = Join-Path $BaseDirectory $Value
    }
    if ($AllowMissing) {
        return [System.IO.Path]::GetFullPath($candidate)
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$configDirectory = Split-Path -Parent $resolvedConfig
$config = Get-Content -Raw -LiteralPath $resolvedConfig | ConvertFrom-Json

$blankFixture = Resolve-ConfiguredPath $config.BlankFixture $configDirectory "BlankFixture"
$dateStampFixture = Resolve-ConfiguredPath $config.DateStampFixture $configDirectory "DateStampFixture"
$dllPath = Resolve-ConfiguredPath $config.DllPath $configDirectory "DllPath" -AllowMissing
$resolvedSearchPaths = @()
foreach ($searchPath in @($config.DllSearchPaths)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$searchPath)) {
        $resolvedSearchPaths += Resolve-ConfiguredPath ([string]$searchPath) $configDirectory "DllSearchPaths" -AllowMissing
    }
}
if ($resolvedSearchPaths.Count -gt 0) {
    $env:DOCUWORKS_XDWAPI_PATHS = $resolvedSearchPaths -join [System.IO.Path]::PathSeparator
} else {
    Remove-Item Env:DOCUWORKS_XDWAPI_PATHS -ErrorAction SilentlyContinue
}

$artifactSetting = $config.ArtifactBase
if ([string]::IsNullOrWhiteSpace($artifactSetting)) {
    $artifactSetting = ".\integration-runs"
}
$artifactBase = Resolve-ConfiguredPath $artifactSetting $configDirectory "ArtifactBase" -AllowMissing
New-Item -ItemType Directory -Force -Path $artifactBase | Out-Null

$runnerCandidates = @(
    (Join-Path $PSScriptRoot "run_integration.ps1"),
    (Join-Path $PSScriptRoot "run_integration_0.3.0.ps1")
)
$runner = $runnerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $runner) {
    throw "run_integration.ps1 or run_integration_0.3.0.ps1 was not found beside this command."
}

$runId = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$artifactRoot = Join-Path $artifactBase $runId
$arguments = @{
    BlankFixture = $blankFixture
    DateStampFixture = $dateStampFixture
    ArtifactRoot = $artifactRoot
}
if (-not [string]::IsNullOrWhiteSpace($dllPath)) {
    if (-not (Test-Path -LiteralPath $dllPath -PathType Leaf)) {
        throw "DllPath does not exist: $dllPath"
    }
    $arguments.DllPath = $dllPath
}
if ($null -ne $config.CodePage -and [int]$config.CodePage -gt 0) {
    $arguments.CodePage = [int]$config.CodePage
}

Write-Host "Run ID: $runId"
Write-Host "Artifact directory: $artifactRoot"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner @arguments
$runExitCode = $LASTEXITCODE

$latestPath = Join-Path $artifactBase "latest-run.txt"
[System.IO.File]::WriteAllText($latestPath, $artifactRoot + [Environment]::NewLine)
Write-Host "Latest run pointer: $latestPath"
exit $runExitCode
