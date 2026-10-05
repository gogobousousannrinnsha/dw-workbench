[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "release-dist")
)

$ErrorActionPreference = "Stop"
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) {
    if (Get-ChildItem -LiteralPath $output -Force | Select-Object -First 1) {
        throw "OutputDirectory must be empty or new: $output"
    }
} else {
    New-Item -ItemType Directory -Path $output -Force | Out-Null
}

& py -3.11 -m pip wheel $PSScriptRoot --no-deps --no-build-isolation --wheel-dir $output
if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }

$stagingRoot = Join-Path $output "source-staging"
$project = Join-Path $stagingRoot "docuworks-ctypes-1.0.0"
New-Item -ItemType Directory -Path $project -Force | Out-Null
foreach ($directory in @("docuworks_ctypes", "tests", "examples")) {
    Copy-Item -Recurse -LiteralPath (Join-Path $PSScriptRoot $directory) -Destination $project
}
$files = @(
    "pyproject.toml", "README.md", "CORE_VERIFICATION_COMPLETE.md",
    "SIMPLE_API_SPEC_0.7.0.md", "SIMPLE_WORKFLOW_GUIDE_0.8.0.md",
    "SIMPLE_API_REFERENCE_0.9.0.md", "SIMPLE_API_REFERENCE_1.0.md", "SIMPLE_API_ROADMAP.md",
    "PUBLIC_API_1.0.json", "API_STABILITY_1.0.md", "MIGRATION_0.9_TO_1.0.md",
    "COMPATIBILITY_1.0.md", "RELEASE_POLICY.md", "KNOWN_RUNTIME_BEHAVIORS.md",
    "CHANGELOG_1.0.0.md", "TEST_RESULTS_1.0.0.txt", "INTEGRATION_TEST_GUIDE.md",
    "INTEGRATION_TEST_RESULTS_TEMPLATE.md", "integration-test.config.json",
    "generate_runtime_report.py", "generate_standard_coverage.py",
    "verify_evidence_pack.py", "finalize_evidence.ps1", "run_integration.ps1",
    "repeat_integration.ps1", "repeat_integration.cmd",
    "compatibility_smoke.py", "verify_distribution.py", "generate_public_api.py",
    "verify_runtime_matrix.py", "run_runtime_matrix.ps1",
    "run_compatibility_matrix.ps1", "install_test_pythons.ps1",
    "build_release.ps1"
)
foreach ($name in $files) {
    $path = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "missing release file: $name" }
    Copy-Item -LiteralPath $path -Destination $project
}
Get-ChildItem -LiteralPath $project -Recurse -Directory -Filter __pycache__ |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $project -Recurse -File -Filter *.pyc | Remove-Item -Force

$sourceZip = Join-Path $output "docuworks-ctypes-1.0.0-source.zip"
Compress-Archive -LiteralPath $project -DestinationPath $sourceZip -CompressionLevel Optimal
$resolvedStage = [System.IO.Path]::GetFullPath($stagingRoot)
if (-not $resolvedStage.StartsWith($output, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "unsafe staging path: $resolvedStage"
}
Remove-Item -LiteralPath $stagingRoot -Recurse -Force
Write-Host "Release artifacts built: $output"
