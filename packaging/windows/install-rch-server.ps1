param(
    [string] $SourceDir = "$PSScriptRoot\..\..",
    [string] $InstallDir = "$env:ProgramFiles\RCH"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force -Path (Join-Path $SourceDir "bin") -Destination $InstallDir
if (Test-Path (Join-Path $SourceDir "ui")) {
    Copy-Item -Recurse -Force -Path (Join-Path $SourceDir "ui") -Destination $InstallDir
}
Copy-Item -Recurse -Force -Path (Join-Path $SourceDir "packaging") -Destination $InstallDir
if (Test-Path (Join-Path $SourceDir "docs")) {
    Copy-Item -Recurse -Force -Path (Join-Path $SourceDir "docs") -Destination $InstallDir
}
foreach ($name in @("README.md", "LICENSE", "release-manifest.json", "rust-transition.md", "release-readiness-audit.md")) {
    $source = Join-Path $SourceDir $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $InstallDir -Force
    }
}

Write-Host "Installed RCH Rust server to $InstallDir"
Write-Host "Start with: $InstallDir\packaging\windows\start-rch-server.ps1"
