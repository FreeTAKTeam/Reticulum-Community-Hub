param(
    [Parameter(Mandatory)][string] $Repository,
    [Parameter(Mandatory)][string] $Tag,
    [Parameter(Mandatory)][string] $Path,
    [switch] $VerifyOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$files = @(Get-ChildItem -Path $Path -File)
if ($files.Count -eq 0) {
    throw "No release assets match '$Path'."
}

$releaseJson = gh release view --repo $Repository --json assets "--" $Tag
if ($LASTEXITCODE -ne 0) {
    throw "Failed to list assets for release '$Tag' (gh exit $LASTEXITCODE)."
}
$assets = ($releaseJson | ConvertFrom-Json).assets
$existingNames = foreach ($asset in $assets) {
    $asset.name
    $asset.label
}

$missing = @(foreach ($file in $files) {
    if ($existingNames -ccontains $file.Name) {
        Write-Host "Keeping existing release asset $($file.Name)."
    } else {
        $file.FullName
    }
})
if ($missing.Count -eq 0) {
    return
}
if ($VerifyOnly) {
    throw "Missing release assets: $($missing -join ', ')."
}

gh release upload --repo $Repository "--" $Tag @missing
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload missing assets for release '$Tag' (gh exit $LASTEXITCODE)."
}
