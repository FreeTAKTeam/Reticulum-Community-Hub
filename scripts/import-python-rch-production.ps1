param(
    [string] $SourceRoot = (Get-Location).Path,
    [string] $LegacyStore = "",
    [string] $TargetDir = "",
    [string] $ReticulumConfig = (Join-Path $env:USERPROFILE ".reticulum\config"),
    [string] $TransportIdentity = (Join-Path $env:USERPROFILE ".reticulum\storage\transport_identity"),
    [string] $SourceManifest = "",
    [string] $CargoToolchain = "+1.85.0",
    [switch] $Force
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string] $Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Copy-IfExists {
    param(
        [string] $Source,
        [string] $Destination,
        [string] $Role
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Warning "$Role not found: $Source"
        return $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Write-Host "Copied ${Role}: $Source -> $Destination"
    return $true
}

function Add-ManifestItem {
    param(
        [System.Collections.Generic.List[object]] $Items,
        [string] $Role,
        [string] $Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        $Items.Add([pscustomobject]@{
            role = $Role
            path = $Path
            exists = $false
        })
        return
    }
    $item = Get-Item -LiteralPath $Path
    $hash = if (-not $item.PSIsContainer) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash } else { "" }
    $Items.Add([pscustomobject]@{
        role = $Role
        path = $item.FullName
        exists = $true
        length = if ($item.PSIsContainer) { $null } else { $item.Length }
        last_write_time = $item.LastWriteTime.ToString("o")
        sha256 = $hash
    })
}

function Convert-ReticulumConfig {
    param(
        [string] $Source,
        [string] $Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
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

    $output = @(
        "# Generated from legacy Reticulum config by import-python-rch-production.ps1.",
        "# Server transport is supplied at daemon startup with --transport."
    )
    foreach ($section in $sections) {
        $enabled = "$($section.interface_enabled)".ToLowerInvariant()
        if ("$($section.type)" -ne "TCPClientInterface" -or @("false", "no", "0") -contains $enabled) {
            continue
        }
        if (-not $section.target_host -or -not $section.target_port) {
            continue
        }
        $name = "$($section.name)".Replace("\", "\\").Replace('"', '\"')
        $targetHost = "$($section.target_host)".Replace("\", "\\").Replace('"', '\"')
        $output += ""
        $output += "[[interfaces]]"
        $output += 'type = "tcp_client"'
        $output += "enabled = true"
        $output += "name = `"$name`""
        $output += "host = `"$targetHost`""
        $output += "port = $($section.target_port)"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Set-Content -LiteralPath $Destination -Value $output -Encoding UTF8
    Write-Host "Wrote reticulumd config: $Destination"
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

if (-not (Test-Path -LiteralPath $legacyDb)) {
    throw "Legacy Python database not found: $legacyDb"
}
if ((Test-Path -LiteralPath $targetDb) -and -not $Force) {
    throw "Target DB already exists: $targetDb. Re-run with -Force to replace it."
}

New-Item -ItemType Directory -Force -Path $targetDirPath | Out-Null
if ((Test-Path -LiteralPath $targetDb) -and $Force) {
    Remove-Item -LiteralPath $targetDb -Force
}

Copy-IfExists -Source $legacyConfig -Destination (Join-Path $targetDirPath "config.ini") -Role "RTH config.ini" | Out-Null
Copy-IfExists -Source (Join-Path $legacyStorePath "identity") -Destination (Join-Path $targetDirPath "identity") -Role "RTH identity" | Out-Null
Copy-IfExists -Source $TransportIdentity -Destination (Join-Path $targetDirPath "reticulumd.identity") -Role "Reticulum transport identity" | Out-Null
Copy-IfExists -Source $legacyTelemetry -Destination (Join-Path $targetDirPath "telemetry.legacy.db") -Role "RTH telemetry.db" | Out-Null
Copy-IfExists -Source $rootTelemetry -Destination (Join-Path $targetDirPath "telemetry.root.legacy.db") -Role "root telemetry.db" | Out-Null
Copy-IfExists -Source $ReticulumConfig -Destination (Join-Path $targetDirPath "reticulum-legacy.config") -Role "Reticulum config" | Out-Null
Convert-ReticulumConfig -Source $ReticulumConfig -Destination (Join-Path $targetDirPath "reticulumd.toml")

$migratorArgs = @(
    "--legacy-db", $legacyDb,
    "--target-db", $targetDb,
    "--report-json"
)
if (Test-Path -LiteralPath $legacyConfig) {
    $migratorArgs += @("--legacy-config", $legacyConfig)
}
if (Test-Path -LiteralPath $legacyTelemetry) {
    $migratorArgs += @("--legacy-telemetry-db", $legacyTelemetry)
}
if (Test-Path -LiteralPath $rootTelemetry) {
    $migratorArgs += @("--legacy-telemetry-db", $rootTelemetry)
}

$cargoArgs = @()
if ($CargoToolchain) {
    $cargoArgs += $CargoToolchain
}
$cargoArgs += @("run", "--release", "-p", "r3akt-rch-core", "--bin", "migrate_python_rch", "--")
& cargo @cargoArgs @migratorArgs | Tee-Object -FilePath $reportPath

if (-not $SourceManifest) {
    $SourceManifest = Join-Path $sourceRootPath "MANIFEST.txt"
    $parentManifest = Join-Path (Split-Path -Parent $sourceRootPath) "MANIFEST.txt"
    if (-not (Test-Path -LiteralPath $SourceManifest) -and (Test-Path -LiteralPath $parentManifest)) {
        $SourceManifest = $parentManifest
    }
}
$sourceManifest = Resolve-FullPath $SourceManifest
$manifestItems = [System.Collections.Generic.List[object]]::new()
Add-ManifestItem -Items $manifestItems -Role "rth_api.sqlite" -Path $legacyDb
Add-ManifestItem -Items $manifestItems -Role "RTH_Store telemetry.db" -Path $legacyTelemetry
Add-ManifestItem -Items $manifestItems -Role "root telemetry.db" -Path $rootTelemetry
Add-ManifestItem -Items $manifestItems -Role "RTH identity" -Path (Join-Path $legacyStorePath "identity")
Add-ManifestItem -Items $manifestItems -Role "Reticulum transport identity" -Path $TransportIdentity
Add-ManifestItem -Items $manifestItems -Role "RTH config.ini" -Path $legacyConfig
Add-ManifestItem -Items $manifestItems -Role "Reticulum config" -Path $ReticulumConfig
Add-ManifestItem -Items $manifestItems -Role "source MANIFEST.txt" -Path $sourceManifest
$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    source_root = $sourceRootPath
    target_dir = $targetDirPath
    target_db = $targetDb
    files = $manifestItems
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $targetDirPath "MANIFEST.txt") -Encoding UTF8

Write-Host "Rust RCH state DB: $targetDb"
Write-Host "Migration report: $reportPath"
Write-Host "Generated manifest: $(Join-Path $targetDirPath "MANIFEST.txt")"
