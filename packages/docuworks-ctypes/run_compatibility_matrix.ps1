[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Wheel,
    [Parameter(Mandatory = $true)] [string]$SourceZip,
    [Parameter(Mandatory = $true)] [string]$BlankFixture,
    [string]$ArtifactRoot,
    [string[]]$Versions = @("3.10", "3.11", "3.12", "3.13")
)

$ErrorActionPreference = "Stop"
$wheelPath = (Resolve-Path -LiteralPath $Wheel).Path
$sourceZipPath = (Resolve-Path -LiteralPath $SourceZip).Path
$fixturePath = (Resolve-Path -LiteralPath $BlankFixture).Path
if (-not $ArtifactRoot) {
    $ArtifactRoot = Join-Path $PSScriptRoot ("compatibility-runs\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$root = [System.IO.Path]::GetFullPath($ArtifactRoot)
if (Test-Path -LiteralPath $root) {
    if (Get-ChildItem -LiteralPath $root -Force | Select-Object -First 1) {
        throw "ArtifactRoot must be empty or new: $root"
    }
} else {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
}

$fixtureBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $fixturePath).Hash
$expanded = Join-Path $root "expanded-source"
Expand-Archive -LiteralPath $sourceZipPath -DestinationPath $expanded
$sourceProject = Get-ChildItem -LiteralPath $expanded -Recurse -Filter pyproject.toml -File |
    Select-Object -First 1 | ForEach-Object DirectoryName
if (-not $sourceProject) {
    throw "Source ZIP does not contain pyproject.toml"
}

$payload = Join-Path $root "test-payload"
New-Item -ItemType Directory -Path $payload | Out-Null
Copy-Item -Recurse -LiteralPath (Join-Path $sourceProject "tests") -Destination $payload
Copy-Item -Recurse -LiteralPath (Join-Path $sourceProject "examples") -Destination $payload
Copy-Item -LiteralPath (Join-Path $sourceProject "generate_standard_coverage.py") -Destination $payload
Copy-Item -LiteralPath (Join-Path $sourceProject "generate_public_api.py") -Destination $payload
Copy-Item -LiteralPath (Join-Path $sourceProject "compatibility_smoke.py") -Destination $payload
Copy-Item -LiteralPath (Join-Path $sourceProject "verify_distribution.py") -Destination $payload
foreach ($document in @(
    "SIMPLE_API_REFERENCE_0.9.0.md",
    "SIMPLE_API_REFERENCE_1.0.md",
    "COMPATIBILITY_1.0.md",
    "RELEASE_POLICY.md",
    "CHANGELOG_1.0.0.md",
    "KNOWN_RUNTIME_BEHAVIORS.md",
    "API_STABILITY_1.0.md",
    "MIGRATION_0.9_TO_1.0.md",
    "PUBLIC_API_1.0.json"
)) {
    Copy-Item -LiteralPath (Join-Path $sourceProject $document) -Destination $payload
}
Get-ChildItem -LiteralPath $payload -Recurse -Directory -Filter __pycache__ |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $payload -Recurse -File -Filter *.pyc | Remove-Item -Force

$wheelhouse = Join-Path $root "wheelhouse"
New-Item -ItemType Directory -Path $wheelhouse | Out-Null
$oldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& py -3.11 -m pip download --disable-pip-version-check --only-binary=:all: `
    --trusted-host pypi.org --trusted-host files.pythonhosted.org `
    --dest $wheelhouse "setuptools>=69" wheel "pytest==9.1.1" `
    "exceptiongroup>=1" 2>&1 |
    Tee-Object -FilePath (Join-Path $root "wheelhouse-download.log")
$downloadExit = $LASTEXITCODE
$ErrorActionPreference = $oldPreference
if ($downloadExit -ne 0) { throw "test tooling wheelhouse download failed" }
$oldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& py -3.10 -m pip download --disable-pip-version-check --only-binary=:all: `
    --trusted-host pypi.org --trusted-host files.pythonhosted.org `
    --dest $wheelhouse "tomli>=1" 2>&1 |
    Tee-Object -FilePath (Join-Path $root "wheelhouse-download.log") -Append
$tomliDownloadExit = $LASTEXITCODE
$ErrorActionPreference = $oldPreference
if ($tomliDownloadExit -ne 0) { throw "Python 3.10 tomli wheel download failed" }

$results = @()
foreach ($version in $Versions) {
    $pythonOutput = @(& py "-$version" -c "import sys; print(sys.executable)" 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Python $version is unavailable. Run install_test_pythons.ps1 first."
    }
    $basePython = [string]$pythonOutput[-1]
    $versionRoot = Join-Path $root ("python-" + $version)
    New-Item -ItemType Directory -Path $versionRoot | Out-Null

    foreach ($kind in @("wheel", "source")) {
        $environmentRoot = Join-Path $versionRoot $kind
        $venv = Join-Path $environmentRoot "venv"
        New-Item -ItemType Directory -Path $environmentRoot | Out-Null
        & $basePython -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed: Python $version $kind" }
        $python = Join-Path $venv "Scripts\python.exe"
        $setupLog = Join-Path $environmentRoot "install.log"
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $python -m pip install --disable-pip-version-check --no-index --find-links $wheelhouse `
            "setuptools>=69" wheel "pytest==9.1.1" 2>&1 |
            Tee-Object -FilePath $setupLog
        $toolingExit = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
        if ($toolingExit -ne 0) { throw "test tooling install failed: Python $version $kind" }
        $packageTarget = if ($kind -eq "wheel") { $wheelPath } else { $sourceProject }
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $python -m pip install --disable-pip-version-check --no-index --no-build-isolation `
            --no-deps $packageTarget 2>&1 |
            Tee-Object -FilePath $setupLog -Append
        $packageExit = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
        if ($packageExit -ne 0) { throw "package install failed: Python $version $kind" }

        $importJson = Join-Path $environmentRoot "import.json"
        $probe = "import json,docuworks_ctypes,platform,struct,sys; assert docuworks_ctypes.__version__=='1.0.0'; print(json.dumps({'version':docuworks_ctypes.__version__,'module':docuworks_ctypes.__file__,'python':sys.version,'executable':sys.executable,'bits':struct.calcsize('P')*8,'platform':platform.platform()}))"
        Push-Location $environmentRoot
        try {
            & $python -c $probe | Set-Content -Encoding UTF8 -LiteralPath $importJson
            $importExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($importExit -ne 0) { throw "import probe failed: Python $version $kind" }
        $importData = Get-Content -Raw -LiteralPath $importJson | ConvertFrom-Json
        if (-not ([string]$importData.module).StartsWith($venv, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "import escaped fresh venv: $($importData.module)"
        }
        if ([int]$importData.bits -ne 64) { throw "Python $version is not 64-bit" }

        $junit = Join-Path $environmentRoot "contract-junit.xml"
        $contractLog = Join-Path $environmentRoot "contract.log"
        Push-Location $environmentRoot
        try {
            $oldPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & $python -m pytest -q -m "not integration" (Join-Path $payload "tests") `
                --junitxml=$junit 2>&1 | Tee-Object -FilePath $contractLog
            $contractExit = $LASTEXITCODE
            $ErrorActionPreference = $oldPreference
        } finally {
            $ErrorActionPreference = $oldPreference
            Pop-Location
        }
        if ($contractExit -ne 0) { throw "contract failed: Python $version $kind" }
        [xml]$contractXml = Get-Content -Raw -LiteralPath $junit
        $summary = $contractXml.testsuites.testsuite
        $failed = [int]$summary.failures + [int]$summary.errors
        $skipped = [int]$summary.skipped
        if ($failed -ne 0 -or $skipped -ne 0) {
            throw "contract incomplete: Python $version $kind"
        }
        $results += [ordered]@{
            python = $version
            package = $kind
            executable = $importData.executable
            exact_version = $importData.python
            module = $importData.module
            tests = [int]$summary.tests
            failed = $failed
            skipped = $skipped
            verified = $true
        }

        if ($kind -eq "wheel") {
            $smokeResult = Join-Path $environmentRoot "simple-smoke.json"
            $smokeXdw = Join-Path $environmentRoot "simple-smoke.xdw"
            & $python (Join-Path $payload "compatibility_smoke.py") `
                --fixture $fixturePath --output-xdw $smokeXdw --result $smokeResult
            if ($LASTEXITCODE -ne 0) { throw "Simple smoke failed: Python $version" }
        }
    }
}

$fixtureAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $fixturePath).Hash
if ($fixtureAfter -ne $fixtureBefore) { throw "Blank fixture was modified" }
$matrix = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    wheel = $wheelPath
    source_zip = $sourceZipPath
    fixture = $fixturePath
    fixture_sha256_before = $fixtureBefore
    fixture_sha256_after = $fixtureAfter
    requested_versions = $Versions
    environments = $results
    verified = ($results.Count -eq ($Versions.Count * 2))
}
$matrix | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $root "compatibility-matrix.json")
if (-not $matrix.verified) { exit 1 }
Write-Host "Compatibility matrix verified: $root"
