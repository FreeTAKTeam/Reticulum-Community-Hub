$ErrorActionPreference = "Stop"

$script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$script:ScriptUnderTest = Join-Path $script:RepoRoot "scripts\import-python-rch-production.ps1"

function Assert-True {
    param(
        [bool] $Condition,
        [string] $Message
    )
    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

function Assert-FileExists {
    param([string] $Path)
    Assert-True (Test-Path -LiteralPath $Path -PathType Leaf) "Expected file to exist: $Path"
}

function Assert-FileMissing {
    param([string] $Path)
    Assert-True (-not (Test-Path -LiteralPath $Path)) "Expected path to be absent: $Path"
}

function New-TestMigrationFixture {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "rch-v3-migration-test-$([guid]::NewGuid())"
    $sourceRoot = Join-Path $root "source"
    $store = Join-Path $sourceRoot "RTH_Store"
    $reticulum = Join-Path $root "reticulum"
    New-Item -ItemType Directory -Force -Path $store | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $store "files") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $store "images") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $store "lxmf") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $reticulum "storage") | Out-Null

    Set-Content -LiteralPath (Join-Path $store "rth_api.sqlite") -Value "sqlite placeholder" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "config.ini") -Value "[server]`nlog_level = debug" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "identity") -Value "rch identity" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "telemetry.db") -Value "store telemetry" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $sourceRoot "telemetry.db") -Value "root telemetry" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "files\field-report.txt") -Value "report" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "images\photo.jpg") -Value "image" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $store "lxmf\state.json") -Value "{}" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $reticulum "storage\transport_identity") -Value "transport identity" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $reticulum "config") -Value @"
[Interface 1]
type = TCPClientInterface
interface_enabled = true
target_host = rmap.world
target_port = 4242
"@ -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $sourceRoot "MANIFEST.txt") -Value "source manifest" -Encoding ASCII

    [pscustomobject]@{
        Root = $root
        SourceRoot = $sourceRoot
        Store = $store
        Target = Join-Path $root "target"
        ReticulumConfig = Join-Path $reticulum "config"
        TransportIdentity = Join-Path $reticulum "storage\transport_identity"
    }
}

function New-FakeMigrator {
    param([string] $Root)
    $path = Join-Path $Root "fake-migrator.ps1"
    Set-Content -LiteralPath $path -Encoding ASCII -Value @'
$ErrorActionPreference = "Stop"
$target = $null
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "--target-db") {
        $target = $args[$i + 1]
    }
}
if (-not $target) {
    throw "missing --target-db"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
Set-Content -LiteralPath $target -Value "target db" -Encoding ASCII
[pscustomobject]@{
    legacy_db_path = "legacy"
    target_db_path = $target
    rows = @{ topics = 1 }
    warnings = @()
} | ConvertTo-Json -Depth 5
'@
    return $path
}

function Test-DryRunWritesPlanWithoutCopyingData {
    $fixture = New-TestMigrationFixture
    try {
        & $script:ScriptUnderTest `
            -SourceRoot $fixture.SourceRoot `
            -LegacyStore $fixture.Store `
            -TargetDir $fixture.Target `
            -ReticulumConfig $fixture.ReticulumConfig `
            -TransportIdentity $fixture.TransportIdentity `
            -DryRun | Out-Null

        $planPath = Join-Path $fixture.Target "migration-plan.json"
        Assert-FileExists $planPath
        Assert-FileMissing (Join-Path $fixture.Target "rch_state.sqlite3")
        Assert-FileMissing (Join-Path $fixture.Target "files\field-report.txt")
        $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
        Assert-True ($plan.mode -eq "dry-run") "Dry-run plan records dry-run mode"
        Assert-True ($plan.preflight.legacy_database.exists -eq $true) "Dry-run preflight includes legacy database"
        Assert-True ($plan.runtime_directories.files.exists -eq $true) "Dry-run inventories files directory"
    } finally {
        Remove-Item -LiteralPath $fixture.Root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-RealRunCopiesRuntimeArtifactsAndWritesManifest {
    $fixture = New-TestMigrationFixture
    $fakeMigrator = New-FakeMigrator -Root $fixture.Root
    try {
        & $script:ScriptUnderTest `
            -SourceRoot $fixture.SourceRoot `
            -LegacyStore $fixture.Store `
            -TargetDir $fixture.Target `
            -ReticulumConfig $fixture.ReticulumConfig `
            -TransportIdentity $fixture.TransportIdentity `
            -MigratorExe $fakeMigrator | Out-Null

        Assert-FileExists (Join-Path $fixture.Target "rch_state.sqlite3")
        Assert-FileExists (Join-Path $fixture.Target "config.ini")
        Assert-FileExists (Join-Path $fixture.Target "identity")
        Assert-FileExists (Join-Path $fixture.Target "reticulumd.identity")
        Assert-FileExists (Join-Path $fixture.Target "telemetry.legacy.db")
        Assert-FileExists (Join-Path $fixture.Target "telemetry.root.legacy.db")
        Assert-FileExists (Join-Path $fixture.Target "files\field-report.txt")
        Assert-FileExists (Join-Path $fixture.Target "images\photo.jpg")
        Assert-FileExists (Join-Path $fixture.Target "lxmf\state.json")
        Assert-FileExists (Join-Path $fixture.Target "reticulumd.toml")
        Assert-FileExists (Join-Path $fixture.Target "migration-manifest.json")
        Assert-FileExists (Join-Path $fixture.Target "rust-migration-report.json")
        $manifest = Get-Content -LiteralPath (Join-Path $fixture.Target "migration-manifest.json") -Raw | ConvertFrom-Json
        Assert-True ($manifest.mode -eq "apply") "Manifest records apply mode"
        Assert-True ($manifest.files.Count -gt 5) "Manifest records migrated artifacts"
    } finally {
        Remove-Item -LiteralPath $fixture.Root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$tests = @(
    "Test-DryRunWritesPlanWithoutCopyingData",
    "Test-RealRunCopiesRuntimeArtifactsAndWritesManifest"
)

foreach ($test in $tests) {
    Write-Host "Running $test"
    & $test
}

Write-Host "All import-python-rch-production tests passed"
