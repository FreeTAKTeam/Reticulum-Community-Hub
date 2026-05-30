param(
    [Parameter(Mandatory = $true)] [string] $PackageName,
    [string] $ReleaseVersion,
    [string] $OutputDir = "dist",
    [string] $ServerBinaryPath,
    [string] $TakServiceBinaryPath,
    [switch] $IncludeTakService,
    [switch] $IncludeUi,
    [ValidateSet("auto", "zip", "tar.gz")] [string] $ArchiveFormat = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Resolve-RequiredPath {
    param(
        [Parameter(Mandatory = $true)] [string] $Path,
        [Parameter(Mandatory = $true)] [string] $Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)] [string] $Source,
        [Parameter(Mandatory = $true)] [string] $Destination
    )

    $sourcePath = Resolve-RequiredPath -Path $Source -Label "source directory"
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $sourcePath -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Get-DefaultBinaryPath {
    param([Parameter(Mandatory = $true)] [string] $Name)

    $suffix = ""
    if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
        $suffix = ".exe"
    }
    return Join-Path (Get-Location).Path "target/release/$Name$suffix"
}

if ([string]::IsNullOrWhiteSpace($ServerBinaryPath)) {
    $ServerBinaryPath = Get-DefaultBinaryPath "r3akt-rch-server"
}
if ($IncludeTakService -and [string]::IsNullOrWhiteSpace($TakServiceBinaryPath)) {
    $TakServiceBinaryPath = Get-DefaultBinaryPath "r3akt-tak-service"
}

$serverBinary = Resolve-RequiredPath -Path $ServerBinaryPath -Label "server binary"
$takServiceBinary = $null
if ($IncludeTakService) {
    $takServiceBinary = Resolve-RequiredPath -Path $TakServiceBinaryPath -Label "TAK service binary"
}

$outputPath = New-Item -ItemType Directory -Force -Path $OutputDir
$resolvedOutput = (Resolve-Path -LiteralPath $outputPath.FullName).Path
$stagePath = Join-Path $resolvedOutput $PackageName
$resolvedStageParent = [System.IO.Path]::GetFullPath($resolvedOutput)
$resolvedStage = [System.IO.Path]::GetFullPath($stagePath)
if (-not $resolvedStage.StartsWith($resolvedStageParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to stage package outside output directory: $resolvedStage"
}
if (Test-Path -LiteralPath $resolvedStage) {
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}

New-Item -ItemType Directory -Force -Path `
    (Join-Path $resolvedStage "bin"), `
    (Join-Path $resolvedStage "packaging"), `
    (Join-Path $resolvedStage "packaging/server"), `
    (Join-Path $resolvedStage "packaging/windows") | Out-Null

Copy-Item -LiteralPath $serverBinary -Destination (Join-Path $resolvedStage "bin") -Force
if ($IncludeTakService) {
    Copy-Item -LiteralPath $takServiceBinary -Destination (Join-Path $resolvedStage "bin") -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $resolvedStage "packaging/tak-service") | Out-Null
    Copy-DirectoryContents -Source "packaging/tak-service" -Destination (Join-Path $resolvedStage "packaging/tak-service")
    Copy-Item -LiteralPath "packaging/windows/start-rch-tak-service.ps1" -Destination (Join-Path $resolvedStage "packaging/windows") -Force
}

Copy-Item -LiteralPath "README.md" -Destination $resolvedStage -Force
Copy-Item -LiteralPath "docs/rust-transition.md" -Destination $resolvedStage -Force
Copy-Item -LiteralPath "docs/release-readiness-audit.md" -Destination $resolvedStage -Force
Copy-Item -LiteralPath "packaging/README.md" -Destination (Join-Path $resolvedStage "packaging") -Force
Copy-DirectoryContents -Source "packaging/server" -Destination (Join-Path $resolvedStage "packaging/server")
Copy-Item -LiteralPath "packaging/windows/install-rch-server.ps1" -Destination (Join-Path $resolvedStage "packaging/windows") -Force
Copy-Item -LiteralPath "packaging/windows/start-rch-server.ps1" -Destination (Join-Path $resolvedStage "packaging/windows") -Force

if ($IncludeUi) {
    Copy-DirectoryContents -Source "ui/dist" -Destination (Join-Path $resolvedStage "ui")
}

$manifest = [ordered]@{
    package_name = $PackageName
    release_version = $ReleaseVersion
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    git_ref = [Environment]::GetEnvironmentVariable("GITHUB_REF_NAME")
    git_sha = [Environment]::GetEnvironmentVariable("GITHUB_SHA")
    includes_server = $true
    includes_tak_service = [bool]$IncludeTakService
    includes_ui = [bool]$IncludeUi
    binaries = @((Split-Path -Leaf $serverBinary))
}
if ($IncludeTakService) {
    $manifest.binaries += (Split-Path -Leaf $takServiceBinary)
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $resolvedStage "release-manifest.json") -Encoding utf8

if ($ArchiveFormat -eq "auto") {
    if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
        $ArchiveFormat = "zip"
    } else {
        $ArchiveFormat = "tar.gz"
    }
}

if ($ArchiveFormat -eq "zip") {
    $archivePath = Join-Path $resolvedOutput "$PackageName.zip"
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    Compress-Archive -Path (Join-Path $resolvedStage "*") -DestinationPath $archivePath -Force
} else {
    $archivePath = Join-Path $resolvedOutput "$PackageName.tar.gz"
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    tar -C $resolvedStage -czf $archivePath .
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }
}

$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
"$($hash.Hash)  $(Split-Path -Leaf $archivePath)" | Set-Content -LiteralPath "$archivePath.sha256" -Encoding ascii

[pscustomobject]@{
    package = $PackageName
    archive = $archivePath
    checksum = "$archivePath.sha256"
    stage = $resolvedStage
} | ConvertTo-Json -Compress
