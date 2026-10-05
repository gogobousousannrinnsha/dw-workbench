param(
    [Parameter(Mandatory=$true)][string]$InputXdw,
    [Parameter(Mandatory=$true)][string]$RunDir,
    [Parameter(Mandatory=$true)][string]$DllPath,
    [int]$Page = 1,
    [ValidateSet(300,600)][int]$Dpi = 300,
    [string]$ModelRoot = 'models',
    [string]$Python = '.venv-ocr/Scripts/python.exe'
)
$ErrorActionPreference = 'Stop'
# Run from the repository root. The library refuses existing run directories.
& $Python scripts/verify_models.py --model-root $ModelRoot
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed' }
& $Python -m docuworks_integrations ocr-xdw --input-xdw $InputXdw --run-dir $RunDir --model-root $ModelRoot --page $Page --dpi $Dpi --dll-path $DllPath
if ($LASTEXITCODE -ne 0) { throw 'OCR failed' }
