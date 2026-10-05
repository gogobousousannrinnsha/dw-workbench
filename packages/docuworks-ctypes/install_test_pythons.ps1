[CmdletBinding()]
param(
    [string[]]$Versions = @("3.10", "3.11", "3.12", "3.13")
)

$ErrorActionPreference = "Stop"

function Test-PythonVersion([string]$Version) {
    $registered = @(& py -0p)
    return [bool]($registered | Where-Object { $_ -match "-V:$([regex]::Escape($Version))(?:\s|\*)" })
}

foreach ($version in $Versions) {
    if (Test-PythonVersion $version) {
        Write-Host "Python $version is already registered with py launcher."
        continue
    }
    $packageId = "Python.Python.$version"
    Write-Host "Installing $packageId for the current user..."
    $installerOptions = "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Include_tcltk=0 Include_pip=1 Include_dev=1"
    & winget install --source winget --id $packageId --exact --scope user --silent `
        --accept-package-agreements --accept-source-agreements --override $installerOptions
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed for $packageId with exit code $LASTEXITCODE"
    }
}

$missing = @()
foreach ($version in $Versions) {
    if (Test-PythonVersion $version) {
        & py "-$version" -c "import sys; print(sys.version); print(sys.executable)"
    } else {
        $missing += $version
    }
}
if ($missing.Count -gt 0) {
    throw "Python versions are still unavailable: $($missing -join ', '). Restart the shell and rerun."
}
