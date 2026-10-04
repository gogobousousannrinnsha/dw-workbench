param(
    [string]$Manifest = (Join-Path $PSScriptRoot 'PORTABLE-MANIFEST.json'),
    [string]$Destination = $PSScriptRoot,
    [switch]$Extract
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Get-SafeChild([string]$Parent, [string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name) -or [IO.Path]::GetFileName($Name) -ne $Name -or $Name -match '[\\/:]') {
        throw "Invalid file name in manifest: $Name"
    }
    $parentPath = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $path = [IO.Path]::GetFullPath((Join-Path $Parent $Name))
    if (-not $path.StartsWith($parentPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The output path is outside the selected folder.'
    }
    return $path
}
function Assert-Hash([string]$Path, [long]$Bytes, [string]$Expected) {
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid SHA-256 in manifest.' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing download: $([IO.Path]::GetFileName($Path))" }
    if ((Get-Item -LiteralPath $Path).Length -ne $Bytes) { throw "Size mismatch: $([IO.Path]::GetFileName($Path))" }
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $inputStream = [IO.File]::OpenRead($Path)
    try { $actual = [BitConverter]::ToString($algorithm.ComputeHash($inputStream)).Replace('-', '') }
    finally { $inputStream.Dispose(); $algorithm.Dispose() }
    if ($actual -ne $Expected) { throw "SHA-256 mismatch: $([IO.Path]::GetFileName($Path))" }
}

$base = [IO.Path]::GetFullPath($PSScriptRoot)
$data = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ($data.format -ne 'dw-workbench-portable-parts-v1') { throw 'Unsupported manifest format.' }
$zipPath = Get-SafeChild $base $data.zip.name
$temporaryZip = Get-SafeChild $base ($data.zip.name + '.' + [Guid]::NewGuid().ToString('N') + '.partial')
$parts = @($data.parts)
if ($parts.Count -eq 0) { throw 'No parts in manifest.' }

if (Test-Path -LiteralPath $zipPath) {
    Assert-Hash $zipPath ([long]$data.zip.bytes) $data.zip.sha256
    Write-Host 'Verified existing complete ZIP.'
} else {
    $sum = [long]0
    foreach ($part in $parts) {
        $partPath = Get-SafeChild $base $part.name
        Write-Host "Checking $($part.name)..."
        Assert-Hash $partPath ([long]$part.bytes) $part.sha256
        $sum += [long]$part.bytes
    }
    if ($sum -ne [long]$data.zip.bytes) { throw 'The part sizes do not match the complete ZIP.' }
    $output = $null
    try {
        $output = [IO.File]::Open($temporaryZip, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        foreach ($part in $parts) {
            $inputStream = [IO.File]::OpenRead((Get-SafeChild $base $part.name))
            try { $inputStream.CopyTo($output, 8MB) } finally { $inputStream.Dispose() }
        }
        $output.Flush($true)
        $output.Dispose()
        $output = $null
        Assert-Hash $temporaryZip ([long]$data.zip.bytes) $data.zip.sha256
        Move-Item -LiteralPath $temporaryZip -Destination $zipPath
        Write-Host 'Complete ZIP restored and verified.'
    } finally {
        if ($null -ne $output) { $output.Dispose() }
        if (Test-Path -LiteralPath $temporaryZip) { Remove-Item -LiteralPath $temporaryZip }
    }
}

if ($Extract) {
    if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { throw 'The destination folder must already exist.' }
    $destinationPath = [IO.Path]::GetFullPath($Destination)
    $target = Get-SafeChild $destinationPath $data.root_directory
    if (Test-Path -LiteralPath $target) { throw 'The Portable folder already exists. Select another destination; existing work is preserved.' }
    $temporaryDirectory = Get-SafeChild $destinationPath ('DW-Workbench-extract-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $expectedPrefix = $data.root_directory + '/'
        $absolutePrefix = $temporaryDirectory.TrimEnd('\') + '\'
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if (-not $name.StartsWith($expectedPrefix, [StringComparison]::Ordinal) -or $name.Contains(':')) { throw 'Unexpected directory in ZIP.' }
            $resolved = [IO.Path]::GetFullPath((Join-Path $temporaryDirectory $name.Replace('/', '\')))
            if (-not $resolved.StartsWith($absolutePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe file path in ZIP.' }
        }
    } finally { $archive.Dispose() }
    Write-Host 'Extracting the Portable folder...'
    [IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $temporaryDirectory)
    $extracted = Get-SafeChild $temporaryDirectory $data.root_directory
    if (-not (Test-Path -LiteralPath (Join-Path $extracted 'runtime\python.exe'))) { throw 'The extracted runtime is incomplete.' }
    Move-Item -LiteralPath $extracted -Destination $target
    Remove-Item -LiteralPath $temporaryDirectory
    Write-Host "Ready: $target"
    Write-Host 'Open the folder, read the introduction, then run the startup BAT.'
}
