[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunDirectory,

    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$run = (Resolve-Path -LiteralPath $RunDirectory).Path.TrimEnd("\")
$viewerPath = Join-Path $run "viewer-verification.json"
$statusPath = Join-Path $run "verification-status.json"
$manifestPath = Join-Path $run "artifact-manifest.json"

if (-not (Test-Path -LiteralPath $viewerPath -PathType Leaf)) {
    throw "viewer-verification.json was not found: $viewerPath"
}

$viewer = Get-Content -Raw -LiteralPath $viewerPath | ConvertFrom-Json
$requiredViewerItems = @(
    "annotation_display",
    "text_rendering",
    "no_corruption_warning",
    "annotation_reeditable",
    "ascii_document_format_unchanged"
)
foreach ($name in $requiredViewerItems) {
    if ($null -eq $viewer.items.$name -or $null -eq $viewer.items.$name.verified) {
        throw "viewer-verification.json is missing items.$name.verified"
    }
}
$anyViewerItemVerified = @(
    $requiredViewerItems | Where-Object {
        [bool]$viewer.items.PSObject.Properties[$_].Value.verified
    }
).Count -gt 0
if ($anyViewerItemVerified -and (
    [string]::IsNullOrWhiteSpace([string]$viewer.verified_at) -or
    [string]::IsNullOrWhiteSpace([string]$viewer.verified_by)
)) {
    throw "verified_at and verified_by are required when a Viewer item is verified"
}

$visualEditVerified = (
    [bool]$viewer.items.annotation_display.verified -and
    [bool]$viewer.items.text_rendering.verified -and
    [bool]$viewer.items.no_corruption_warning.verified -and
    [bool]$viewer.items.annotation_reeditable.verified
)
$formatVerified = [bool]$viewer.items.ascii_document_format_unchanged.verified
$annotationTypeNames = @(
    "TEXT", "LINK", "STICKY", "STRAIGHT_LINE", "RECTANGLE",
    "ELLIPSE", "DATE_STAMP", "MARKER", "POLYGON"
)
$requiresTypeReview = ([int]$viewer.schema_version -ge 2)
$annotationTypesVerified = $true
if ($requiresTypeReview) {
    foreach ($name in $annotationTypeNames) {
        if ($null -eq $viewer.annotation_types.$name -or
            -not [bool]$viewer.annotation_types.$name.verified) {
            $annotationTypesVerified = $false
        }
    }
}
$viewerVerified = $visualEditVerified -and $formatVerified -and $annotationTypesVerified

if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
    $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
} else {
    $status = [pscustomobject]@{}
}
$status | Add-Member -NotePropertyName viewer_visual_edit_verified -NotePropertyValue $visualEditVerified -Force
$status | Add-Member -NotePropertyName viewer_format_verified -NotePropertyValue $formatVerified -Force
$status | Add-Member -NotePropertyName viewer_annotation_types_verified -NotePropertyValue $annotationTypesVerified -Force
$status | Add-Member -NotePropertyName viewer_verified -NotePropertyValue $viewerVerified -Force
if ($viewerVerified) {
    $viewerVerification = "VERIFIED"
} elseif ($visualEditVerified) {
    $viewerVerification = "FORMAT_PENDING"
} else {
    $viewerVerification = "PENDING_REVIEW"
}
$status | Add-Member -NotePropertyName viewer_verification -NotePropertyValue $viewerVerification -Force
$status | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $statusPath

$coveragePath = Join-Path $run "standard-coverage.json"
if ((Test-Path -LiteralPath $coveragePath -PathType Leaf) -and $requiresTypeReview) {
    $coverage = Get-Content -Raw -LiteralPath $coveragePath | ConvertFrom-Json
    foreach ($row in $coverage.rows) {
        $typeReview = $viewer.annotation_types.PSObject.Properties[$row.annotation_type]
        if ($null -ne $typeReview -and [bool]$typeReview.Value.verified) {
            $row.viewer = "REPRESENTATIVE_TYPE_VERIFIED"
        } else {
            $row.viewer = "REPRESENTATIVE_TYPE_PENDING"
        }
    }
    $coverage | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $coveragePath
}

$requiredFiles = @(
    "run-manifest.json",
    "runtime-resolution.json",
    "runtime-report-console.log",
    "environment.json",
    "contract-junit.xml",
    "contract-console.log",
    "integration-junit.xml",
    "integration-console.log",
    "evidence.jsonl",
    "standard-coverage.json",
    "verification-status.json",
    "viewer-verification.json"
)
$missingRequired = @(
    $requiredFiles | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $run $_) -PathType Leaf)
    }
)
$xdwFiles = @(Get-ChildItem -LiteralPath (Join-Path $run "xdw") -Filter *.xdw -File -ErrorAction SilentlyContinue)
if ($xdwFiles.Count -eq 0) {
    $missingRequired += "xdw/*.xdw"
}
$prefix = $run + "\"
$entries = @(
    Get-ChildItem -LiteralPath $run -Recurse -File |
        Where-Object { $_.FullName -ne $manifestPath } |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($prefix.Length).Replace("\", "/")
                size = $_.Length
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
            }
        }
)
$manifest = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    run_directory = $run
    missing_required_files = $missingRequired
    files = $entries
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $manifestPath

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $parent = Split-Path -Parent $run
    $leaf = Split-Path -Leaf $run
    $OutputPath = Join-Path $parent "$leaf-evidence.zip"
}
$archive = [System.IO.Path]::GetFullPath($OutputPath)
if ($archive.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputPath must be outside RunDirectory: $archive"
}
if (Test-Path -LiteralPath $archive) {
    $directory = Split-Path -Parent $archive
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($archive)
    $archive = Join-Path $directory ("{0}-{1}.zip" -f $stem, (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
}
Compress-Archive -Path (Join-Path $run "*") -DestinationPath $archive -CompressionLevel Optimal
$verifier = Join-Path $PSScriptRoot "verify_evidence_pack.py"
& py $verifier $archive
if ($LASTEXITCODE -ne 0) {
    throw "Evidence archive verification failed with exit code $LASTEXITCODE"
}

Write-Host "Evidence archive: $archive"
Write-Host "Missing required files: $($missingRequired.Count)"
Write-Host "Viewer visual/edit verified: $visualEditVerified"
Write-Host "Viewer format verified: $formatVerified"
Write-Host "Viewer annotation types verified: $annotationTypesVerified"
Write-Host "Viewer verified: $viewerVerified"
