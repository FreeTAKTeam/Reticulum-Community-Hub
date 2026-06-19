[CmdletBinding()]
param(
    [string] $SourceRoot = (Get-Location).Path,
    [string] $LegacyStore = "",
    [string] $TargetDir = "",
    [string] $ReticulumConfig = (Join-Path $env:USERPROFILE ".reticulum\config"),
    [string] $TransportIdentity = (Join-Path $env:USERPROFILE ".reticulum\storage\transport_identity"),
    [string] $SourceManifest = "",
    [string] $CargoToolchain = "+1.85.0",
    [string] $MigratorExe = "",
    [switch] $Force,
    [switch] $DryRun,
    [switch] $SkipRuntimeFiles
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-FullPath {
    param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Write-JsonFile {
    param(
        [string] $Path,
        [object] $Value
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $json = $Value | ConvertTo-Json -Depth 8
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, "$json`n", $encoding)
}

function Copy-IfExists {
    param(
        [string] $Source,
        [string] $Destination,
        [string] $Role
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        Write-Warning "$Role not found: $Source"
        return $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Write-Host "Copied ${Role}: $Source -> $Destination"
    return $true
}

function Copy-DirectoryIfExists {
    param(
        [string] $Source,
        [string] $Destination,
        [string] $Role
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        Write-Warning "$Role not found: $Source"
        return $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    Write-Host "Copied ${Role}: $Source -> $Destination"
    return $true
}

function New-PathInventory {
    param(
        [string] $Role,
        [string] $Path
    )
    $exists = Test-Path -LiteralPath $Path
    $item = if ($exists) { Get-Item -LiteralPath $Path } else { $null }
    $hash = ""
    if ($exists -and -not $item.PSIsContainer) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
    }
    [pscustomobject]@{
        role = $Role
        path = if ($exists) { $item.FullName } else { $Path }
        exists = $exists
        kind = if (-not $exists) { "missing" } elseif ($item.PSIsContainer) { "directory" } else { "file" }
        length = if ($exists -and -not $item.PSIsContainer) { $item.Length } else { $null }
        last_write_time = if ($exists) { $item.LastWriteTime.ToString("o") } else { $null }
        sha256 = $hash
    }
}

function New-DirectoryInventory {
    param(
        [string] $Role,
        [string] $Path
    )
    $base = New-PathInventory -Role $Role -Path $Path
    if (-not $base.exists -or $base.kind -ne "directory") {
        return $base
    }
    $files = Get-ChildItem -LiteralPath $Path -File -Recurse -ErrorAction Stop
    $totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
    $base | Add-Member -NotePropertyName file_count -NotePropertyValue @($files).Count
    $base | Add-Member -NotePropertyName total_bytes -NotePropertyValue $(if ($null -eq $totalBytes) { 0 } else { [int64]$totalBytes })
    return $base
}

function Convert-ReticulumConfig {
    param(
        [string] $Source,
        [string] $Destination
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        Write-Warning "Reticulum config not found: $Source"
        return
    }
    $sections = @()
    $current = $null
    foreach ($rawLine in Get-Content -LiteralPath $Source) {
        $line = $rawLine.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#") -or $line.StartsWith(";")) {
            continue
        }
        if ($line -match '^\[(.+)\]$') {
            if ($null -ne $current) {
                $sections += $current
            }
            $current = [ordered]@{ name = $Matches[1] }
            continue
        }
        if ($null -eq $current -or -not ($line -match '^([^=]+)=(.*)$')) {
            continue
        }
        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        $current[$key] = $value
    }
    if ($null -ne $current) {
        $sections += $current
    }

    function Get-SectionValue {
        param(
            [System.Collections.Specialized.OrderedDictionary] $Section,
            [string] $Key,
            [string] $Default = ""
        )
        if ($Section.Contains($Key)) {
            return "$($Section[$Key])"
        }
        return $Default
    }

    $output = @(
        "# Generated from legacy Reticulum config by import-python-rch-production.ps1.",
        "# Server transport is supplied at daemon startup with --transport."
    )
    foreach ($section in $sections) {
        $enabled = (Get-SectionValue -Section $section -Key "interface_enabled" -Default "true").ToLowerInvariant()
        $type = Get-SectionValue -Section $section -Key "type"
        $targetHostValue = Get-SectionValue -Section $section -Key "target_host"
        $targetPortValue = Get-SectionValue -Section $section -Key "target_port"
        if ($type -ne "TCPClientInterface" -or @("false", "no", "0") -contains $enabled) {
            continue
        }
        if (-not $targetHostValue -or -not $targetPortValue) {
            continue
        }
        $name = (Get-SectionValue -Section $section -Key "name").Replace("\", "\\").Replace('"', '\"')
        $targetHost = $targetHostValue.Replace("\", "\\").Replace('"', '\"')
        $output += ""
        $output += "[[interfaces]]"
        $output += 'type = "tcp_client"'
        $output += "enabled = true"
        $output += "name = `"$name`""
        $output += "host = `"$targetHost`""
        $output += "port = $targetPortValue"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Destination, (($output -join "`n") + "`n"), $encoding)
    Write-Host "Wrote reticulumd config: $Destination"
}

function Invoke-Migrator {
    param(
        [string] $MigratorExe,
        [string] $CargoToolchain,
        [string[]] $MigratorArgs,
        [string] $ReportPath
    )
    if ($MigratorExe) {
        $resolved = Resolve-FullPath $MigratorExe
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "Migrator executable not found: $resolved"
        }
        & $resolved @MigratorArgs | Tee-Object -FilePath $ReportPath
        return
    }
    if (Test-Path -LiteralPath ".\target\release\migrate_python_rch.exe" -PathType Leaf) {
        & ".\target\release\migrate_python_rch.exe" @MigratorArgs | Tee-Object -FilePath $ReportPath
        return
    }
    if (Test-Path -LiteralPath ".\target\debug\migrate_python_rch.exe" -PathType Leaf) {
        & ".\target\debug\migrate_python_rch.exe" @MigratorArgs | Tee-Object -FilePath $ReportPath
        return
    }
    $cargoArgs = @()
    if ($CargoToolchain) {
        $cargoArgs += $CargoToolchain
    }
    $cargoArgs += @("run", "--release", "-p", "r3akt-rch-core", "--bin", "migrate_python_rch", "--")
    & cargo @cargoArgs @MigratorArgs | Tee-Object -FilePath $ReportPath
}

$sourceRootPath = Resolve-FullPath $SourceRoot
if (-not $LegacyStore) {
    $LegacyStore = Join-Path $sourceRootPath "RTH_Store"
}
if (-not $TargetDir) {
    $TargetDir = Join-Path $sourceRootPath "target\production-rch-3"
}
$legacyStorePath = Resolve-FullPath $LegacyStore
$targetDirPath = Resolve-FullPath $TargetDir
$legacyDb = Join-Path $legacyStorePath "rth_api.sqlite"
$legacyConfig = Join-Path $legacyStorePath "config.ini"
$legacyTelemetry = Join-Path $legacyStorePath "telemetry.db"
$rootTelemetry = Join-Path $sourceRootPath "telemetry.db"
$targetDb = Join-Path $targetDirPath "rch_state.sqlite3"
$reportPath = Join-Path $targetDirPath "rust-migration-report.json"
$planPath = Join-Path $targetDirPath "migration-plan.json"
$manifestPath = Join-Path $targetDirPath "migration-manifest.json"

if (-not $SourceManifest) {
    $SourceManifest = Join-Path $sourceRootPath "MANIFEST.txt"
    $parentManifest = Join-Path (Split-Path -Parent $sourceRootPath) "MANIFEST.txt"
    if (-not (Test-Path -LiteralPath $SourceManifest) -and (Test-Path -LiteralPath $parentManifest)) {
        $SourceManifest = $parentManifest
    }
}
$sourceManifest = Resolve-FullPath $SourceManifest

$runtimeDirectories = [ordered]@{
    files = New-DirectoryInventory -Role "RTH files" -Path (Join-Path $legacyStorePath "files")
    images = New-DirectoryInventory -Role "RTH images" -Path (Join-Path $legacyStorePath "images")
    lxmf = New-DirectoryInventory -Role "RTH LXMF runtime data" -Path (Join-Path $legacyStorePath "lxmf")
}
$preflight = [ordered]@{
    legacy_database = New-PathInventory -Role "rth_api.sqlite" -Path $legacyDb
    rth_config = New-PathInventory -Role "RTH config.ini" -Path $legacyConfig
    rth_identity = New-PathInventory -Role "RTH identity" -Path (Join-Path $legacyStorePath "identity")
    rth_telemetry = New-PathInventory -Role "RTH telemetry.db" -Path $legacyTelemetry
    root_telemetry = New-PathInventory -Role "root telemetry.db" -Path $rootTelemetry
    reticulum_config = New-PathInventory -Role "Reticulum config" -Path $ReticulumConfig
    transport_identity = New-PathInventory -Role "Reticulum transport identity" -Path $TransportIdentity
    source_manifest = New-PathInventory -Role "source MANIFEST.txt" -Path $sourceManifest
}
$plan = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = if ($DryRun) { "dry-run" } else { "apply" }
    source_root = $sourceRootPath
    legacy_store = $legacyStorePath
    target_dir = $targetDirPath
    target_db = $targetDb
    force = [bool]$Force
    skip_runtime_files = [bool]$SkipRuntimeFiles
    preflight = $preflight
    runtime_directories = $runtimeDirectories
}

if (-not (Test-Path -LiteralPath $legacyDb -PathType Leaf)) {
    Write-JsonFile -Path $planPath -Value $plan
    throw "Legacy Python database not found: $legacyDb"
}

New-Item -ItemType Directory -Force -Path $targetDirPath | Out-Null
Write-JsonFile -Path $planPath -Value $plan

if ($DryRun) {
    Write-Host "Dry run complete. Migration plan: $planPath"
    return
}

if ((Test-Path -LiteralPath $targetDb -PathType Leaf) -and -not $Force) {
    throw "Target DB already exists: $targetDb. Re-run with -Force to back it up and replace it."
}
if ((Test-Path -LiteralPath $targetDb -PathType Leaf) -and $Force) {
    $backup = "$targetDb.before-v3-migration.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item -LiteralPath $targetDb -Destination $backup -Force
    Remove-Item -LiteralPath $targetDb -Force
    Write-Host "Existing Rust state DB backed up to $backup"
}

Copy-IfExists -Source $legacyConfig -Destination (Join-Path $targetDirPath "config.ini") -Role "RTH config.ini" | Out-Null
Copy-IfExists -Source (Join-Path $legacyStorePath "identity") -Destination (Join-Path $targetDirPath "identity") -Role "RTH identity" | Out-Null
Copy-IfExists -Source $TransportIdentity -Destination (Join-Path $targetDirPath "reticulumd.identity") -Role "Reticulum transport identity" | Out-Null
Copy-IfExists -Source $legacyTelemetry -Destination (Join-Path $targetDirPath "telemetry.legacy.db") -Role "RTH telemetry.db" | Out-Null
Copy-IfExists -Source $rootTelemetry -Destination (Join-Path $targetDirPath "telemetry.root.legacy.db") -Role "root telemetry.db" | Out-Null
Copy-IfExists -Source $ReticulumConfig -Destination (Join-Path $targetDirPath "reticulum-legacy.config") -Role "Reticulum config" | Out-Null
Convert-ReticulumConfig -Source $ReticulumConfig -Destination (Join-Path $targetDirPath "reticulumd.toml")

if (-not $SkipRuntimeFiles) {
    Copy-DirectoryIfExists -Source (Join-Path $legacyStorePath "files") -Destination (Join-Path $targetDirPath "files") -Role "RTH files" | Out-Null
    Copy-DirectoryIfExists -Source (Join-Path $legacyStorePath "images") -Destination (Join-Path $targetDirPath "images") -Role "RTH images" | Out-Null
    Copy-DirectoryIfExists -Source (Join-Path $legacyStorePath "lxmf") -Destination (Join-Path $targetDirPath "lxmf") -Role "RTH LXMF runtime data" | Out-Null
}

$migratorArgs = @(
    "--legacy-db", $legacyDb,
    "--target-db", $targetDb,
    "--report-json"
)
if (Test-Path -LiteralPath $legacyConfig -PathType Leaf) {
    $migratorArgs += @("--legacy-config", $legacyConfig)
}
if (Test-Path -LiteralPath $legacyTelemetry -PathType Leaf) {
    $migratorArgs += @("--legacy-telemetry-db", $legacyTelemetry)
}
if (Test-Path -LiteralPath $rootTelemetry -PathType Leaf) {
    $migratorArgs += @("--legacy-telemetry-db", $rootTelemetry)
}

Invoke-Migrator -MigratorExe $MigratorExe -CargoToolchain $CargoToolchain -MigratorArgs $migratorArgs -ReportPath $reportPath

$manifestItems = [System.Collections.Generic.List[object]]::new()
foreach ($item in $preflight.GetEnumerator()) {
    $manifestItems.Add($item.Value)
}
if (-not $SkipRuntimeFiles) {
    foreach ($item in $runtimeDirectories.GetEnumerator()) {
        $manifestItems.Add($item.Value)
    }
}
$manifestItems.Add((New-PathInventory -Role "Rust state DB" -Path $targetDb))
$manifestItems.Add((New-PathInventory -Role "Rust migration report" -Path $reportPath))
$manifestItems.Add((New-PathInventory -Role "reticulumd.toml" -Path (Join-Path $targetDirPath "reticulumd.toml")))

$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = "apply"
    source_root = $sourceRootPath
    legacy_store = $legacyStorePath
    target_dir = $targetDirPath
    target_db = $targetDb
    force = [bool]$Force
    skip_runtime_files = [bool]$SkipRuntimeFiles
    plan_path = $planPath
    report_path = $reportPath
    files = $manifestItems
}
Write-JsonFile -Path $manifestPath -Value $manifest
Write-JsonFile -Path (Join-Path $targetDirPath "MANIFEST.txt") -Value $manifest

Write-Host "Rust RCH state DB: $targetDb"
Write-Host "Migration report: $reportPath"
Write-Host "Migration plan: $planPath"
Write-Host "Migration manifest: $manifestPath"
