param(
    [string]$Manifest = (Join-Path $PSScriptRoot 'PORTABLE-MANIFEST.json'),
    [string]$Destination = $PSScriptRoot,
    [switch]$Extract
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$phase = 'initialization'
$currentEntry = ''
$currentPath = ''
$temporaryDirectory = $null
$zipVerified = $false
$base = $PSScriptRoot

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

function Get-EntryRelativePath([string]$Name, [string]$RootName) {
    $normalized = $Name.Replace('\', '/')
    $prefix = $RootName + '/'
    if (-not $normalized.StartsWith($prefix, [StringComparison]::Ordinal)) { throw "Unexpected directory in ZIP: $Name" }
    $relative = $normalized.Substring($prefix.Length).TrimEnd('/')
    if ($relative.Length -eq 0) { return '' }
    foreach ($component in $relative.Split('/')) {
        if ([string]::IsNullOrWhiteSpace($component) -or $component -eq '.' -or $component -eq '..' -or
            $component.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $component.EndsWith('.') -or $component.EndsWith(' ') -or
            $component -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Unsafe file path in ZIP: $Name"
        }
    }
    # Components are validated before concatenation. Avoid an extra ZIP-root
    # directory inside staging: it made the old temporary paths 54 chars longer.
    return $relative.Replace('/', '\')
}

try {
    $base = [IO.Path]::GetFullPath($PSScriptRoot)
    $phase = 'reading manifest'
    $data = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($data.format -ne 'dw-workbench-portable-parts-v1') { throw 'Unsupported manifest format.' }
    $zipPath = Get-SafeChild $base $data.zip.name
    $temporaryZip = Get-SafeChild $base ($data.zip.name + '.' + [Guid]::NewGuid().ToString('N') + '.partial')
    $parts = @($data.parts)
    if ($parts.Count -eq 0) { throw 'No parts in manifest.' }

    $phase = 'verifying ZIP / parts'
    if (Test-Path -LiteralPath $zipPath) {
        $currentPath = $zipPath
        Assert-Hash $zipPath ([long]$data.zip.bytes) $data.zip.sha256
        Write-Host 'Verified existing complete ZIP. No part download is needed.'
    } else {
        $sum = [long]0
        foreach ($part in $parts) {
            $currentPath = Get-SafeChild $base $part.name
            Write-Host "Checking $($part.name)..."
            Assert-Hash $currentPath ([long]$part.bytes) $part.sha256
            $sum += [long]$part.bytes
        }
        if ($sum -ne [long]$data.zip.bytes) { throw 'The part sizes do not match the complete ZIP.' }
        $output = $null
        try {
            $phase = 'joining ZIP parts'
            $currentPath = $temporaryZip
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
    $zipVerified = $true

    if ($Extract) {
        $phase = 'preparing destination'
        $currentPath = $Destination
        if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { throw 'The destination folder must already exist.' }
        $destinationPath = [IO.Path]::GetFullPath($Destination)
        $target = Get-SafeChild $destinationPath $data.root_directory
        if (Test-Path -LiteralPath $target) { throw 'The Portable folder already exists. Select another destination; existing work is preserved.' }
        # This directory is the future application root itself, rather than a
        # parent of another DW-Workbench-v0.2.0 directory. Keep its name short.
        $temporaryDirectory = Get-SafeChild $destinationPath ('._dw-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
        if (Test-Path -LiteralPath $temporaryDirectory) { throw 'Temporary directory collision. Run again.' }

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
        try {
            $phase = 'validating ZIP entries'
            $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
            $fileCount = 0
            $maximumPathLength = 0
            foreach ($entry in $archive.Entries) {
                $currentEntry = $entry.FullName
                $relative = Get-EntryRelativePath $entry.FullName $data.root_directory
                $currentPath = $temporaryDirectory
                if ($relative.Length -gt 0) { $currentPath += '\' + $relative }
                # Legacy .NET path limits are checked before any extraction.
                # Modern hosts keep their existing long-path behavior.
                $null = [IO.Path]::GetFullPath($currentPath)
                $finalPath = $target
                if ($relative.Length -gt 0) { $finalPath += '\' + $relative }
                $currentPath = $finalPath
                $null = [IO.Path]::GetFullPath($finalPath)
                if (-not $seen.Add($relative)) { throw "Duplicate file path in ZIP: $($entry.FullName)" }
                $maximumPathLength = [Math]::Max($maximumPathLength, $finalPath.Length)
                if (-not ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\'))) { $fileCount++ }
            }
            if ($null -ne $data.zip.files -and $fileCount -ne [int]$data.zip.files) { throw 'The ZIP file count does not match the manifest.' }
            Write-Host "ZIP entries verified. Files: $fileCount. Longest final path: $maximumPathLength characters."
            if ($maximumPathLength -ge 260) { Write-Host 'Long paths detected. If Windows rejects them, retry with a shorter destination (for example C:\DWRestore).' }

            $phase = 'creating staging directory'
            $currentEntry = ''
            $currentPath = $temporaryDirectory
            [IO.Directory]::CreateDirectory($temporaryDirectory) | Out-Null
            $completed = 0
            $phase = 'extracting ZIP entry'
            foreach ($entry in $archive.Entries) {
                $currentEntry = $entry.FullName
                $relative = Get-EntryRelativePath $entry.FullName $data.root_directory
                $currentPath = $temporaryDirectory
                if ($relative.Length -gt 0) { $currentPath += '\' + $relative }
                if ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\')) {
                    [IO.Directory]::CreateDirectory($currentPath) | Out-Null
                    continue
                }
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($currentPath)) | Out-Null
                $inputStream = $null
                $outputStream = $null
                try {
                    $inputStream = $entry.Open()
                    $outputStream = [IO.File]::Open($currentPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    $inputStream.CopyTo($outputStream, 1MB)
                    if ($outputStream.Length -ne $entry.Length) { throw "Extracted size mismatch: $($entry.FullName)" }
                } finally {
                    if ($null -ne $outputStream) { $outputStream.Dispose() }
                    if ($null -ne $inputStream) { $inputStream.Dispose() }
                }
                $completed++
                if ($completed -eq 1 -or $completed % 500 -eq 0 -or $completed -eq $fileCount) {
                    Write-Host "Extracted $completed / $fileCount files..."
                }
            }
        } finally { $archive.Dispose() }

        $phase = 'checking extracted runtime'
        $currentEntry = 'runtime/python.exe'
        $currentPath = $temporaryDirectory + '\runtime\python.exe'
        if (-not [IO.File]::Exists($currentPath)) { throw 'The extracted runtime is incomplete.' }
        $phase = 'publishing complete Portable folder'
        $currentEntry = ''
        $currentPath = $target
        # Directory.Move refuses an existing target and performs one same-volume
        # rename after all entries succeeded. A failed extraction is never final.
        [IO.Directory]::Move($temporaryDirectory, $target)
        $temporaryDirectory = $null
        Write-Host "Ready: $target"
        Write-Host 'Open the folder, read the introduction, then run the startup BAT.'
    }
} catch {
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $lines.Add('DW-Workbench Portable restoration failed.')
    $lines.Add('Time: ' + [DateTime]::UtcNow.ToString('o'))
    $lines.Add('PowerShell: ' + $PSVersionTable.PSVersion.ToString())
    $lines.Add('Phase: ' + $phase)
    if ($currentEntry) { $lines.Add('ZIP entry: ' + $currentEntry) }
    if ($currentPath) { $lines.Add('Path: ' + $currentPath); $lines.Add('Path length: ' + $currentPath.Length) }
    $exception = $_.Exception
    while ($null -ne $exception) {
        $lines.Add($exception.GetType().FullName + ' (HRESULT 0x' + $exception.HResult.ToString('X8') + '): ' + $exception.Message)
        $exception = $exception.InnerException
    }
    if ($zipVerified) { $lines.Add('The complete ZIP was verified and is preserved. Retry can reuse it; no part download is needed.') }
    $lines.Add('Existing Portable folders and downloaded parts are preserved.')
    if ($temporaryDirectory -and [IO.Directory]::Exists($temporaryDirectory)) {
        $lines.Add('Incomplete extraction: ' + $temporaryDirectory)
        $lines.Add('This is a temporary folder, not a completed Portable. A retry uses a new staging folder.')
    }
    $lines.Add('For a long-path error, select a short empty destination such as C:\DWRestore.')
    $lines.Add('For access or disk-space errors, check the exact message above and the destination permissions/free space.')
    foreach ($line in $lines) { Write-Host $line }
    try {
        $logPath = Get-SafeChild $base ('Restore-Portable-error-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
        [IO.File]::WriteAllLines($logPath, $lines.ToArray(), (New-Object Text.UTF8Encoding($true)))
        Write-Host "Error log: $logPath"
    } catch { Write-Host 'Could not save the error log. Copy the console message above.' }
    exit 1
}
