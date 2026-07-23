param(
    [string] $SourceStore = "RCH_Store",
    [string] $TargetDataDir = "RTH_Store",
    [string] $MigratorExe = "",
    [switch] $Force,
    [switch] $SkipRuntimeFiles
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string] $Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Copy-LegacyFile {
    param(
        [string] $Source,
        [string] $Destination
    )
    if (Test-Path -LiteralPath $Source) {
        $parent = Split-Path -Parent $Destination
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        Write-Host "Copied $Source -> $Destination"
    }
}

function Copy-LegacyDirectory {
    param(
        [string] $Source,
        [string] $Destination
    )
    if (Test-Path -LiteralPath $Source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
        Write-Host "Copied $Source -> $Destination"
    }
}

$sourceStorePath = Resolve-FullPath $SourceStore
$targetDataDirPath = Resolve-FullPath $TargetDataDir
$legacyDb = Join-Path $sourceStorePath "rth_api.sqlite"
$legacyConfig = Join-Path $sourceStorePath "config.ini"
$targetDb = Join-Path $targetDataDirPath "rch_state.sqlite3"
$reportPath = Join-Path $targetDataDirPath "rust-migration-report.json"

if (-not (Test-Path -LiteralPath $legacyDb)) {
    throw "Legacy Python database not found: $legacyDb"
}

New-Item -ItemType Directory -Force -Path $targetDataDirPath | Out-Null

if ((Test-Path -LiteralPath $targetDb) -and -not $Force) {
    $backup = "$targetDb.before-python-migration.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item -LiteralPath $targetDb -Destination $backup -Force
    Write-Host "Existing Rust state DB backed up to $backup"
}

Copy-LegacyFile -Source $legacyConfig -Destination (Join-Path $targetDataDirPath "config.ini")
Copy-LegacyFile -Source (Join-Path $sourceStorePath "identity") -Destination (Join-Path $targetDataDirPath "identity")
Copy-LegacyFile -Source (Join-Path $sourceStorePath "telemetry.db") -Destination (Join-Path $targetDataDirPath "telemetry.db")

if (-not $SkipRuntimeFiles) {
    Copy-LegacyDirectory -Source (Join-Path $sourceStorePath "files") -Destination (Join-Path $targetDataDirPath "files")
    Copy-LegacyDirectory -Source (Join-Path $sourceStorePath "images") -Destination (Join-Path $targetDataDirPath "images")
    Copy-LegacyDirectory -Source (Join-Path $sourceStorePath "lxmf") -Destination (Join-Path $targetDataDirPath "lxmf")
}

$migratorArgs = @(
    "--legacy-db", $legacyDb,
    "--target-db", $targetDb,
    "--report-json"
)
if (Test-Path -LiteralPath $legacyConfig) {
    $migratorArgs += @("--legacy-config", $legacyConfig)
}

if ($MigratorExe -and (Test-Path -LiteralPath $MigratorExe)) {
    & $MigratorExe @migratorArgs | Tee-Object -FilePath $reportPath
} elseif (Test-Path -LiteralPath ".\target\release\migrate_python_rch.exe") {
    & ".\target\release\migrate_python_rch.exe" @migratorArgs | Tee-Object -FilePath $reportPath
} elseif (Test-Path -LiteralPath ".\target\debug\migrate_python_rch.exe") {
    & ".\target\debug\migrate_python_rch.exe" @migratorArgs | Tee-Object -FilePath $reportPath
} else {
    cargo run -p r3akt-rch-core --bin migrate_python_rch -- @migratorArgs | Tee-Object -FilePath $reportPath
}

Write-Host "Rust RCH state DB: $targetDb"
Write-Host "Migration report: $reportPath"
