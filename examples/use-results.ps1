param(
    [Parameter(Mandatory=$true)][ValidateSet('convert','export','plan','mark')][string]$Action,
    [Parameter(Mandatory=$true)][string]$RunDir,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$RegionId,
    [string]$InputXdw,
    [string]$DllPath,
    [string]$Python = '.venv-results/Scripts/python.exe'
)
$ErrorActionPreference = 'Stop'
$cliArgs = @('-m','docuworks_integrations')
switch ($Action) {
    'convert' { $cliArgs += @('convert-ocr-run','--run-dir',$RunDir,'--output-dir',$Output) }
    'export' { $cliArgs += @('export-ocr','--run-dir',$RunDir,'--format','jsonl','--output',$Output) }
    default {
        if (-not $RegionId) { throw 'RegionId is required for plan/mark' }
        if ($Action -eq 'mark' -and -not $DllPath) { throw 'DllPath is required for mark' }
        $cliArgs += @('mark-region','--run-dir',$RunDir,'--region-id',$RegionId,'--output-xdw',$Output)
        if ($InputXdw) { $cliArgs += @('--input-xdw',$InputXdw) }
        if ($DllPath) { $cliArgs += @('--dll-path',$DllPath) }
        if ($Action -eq 'plan') { $cliArgs += '--dry-run' }
    }
}
& $Python @cliArgs
if ($LASTEXITCODE -ne 0) { throw 'Result operation failed' }
