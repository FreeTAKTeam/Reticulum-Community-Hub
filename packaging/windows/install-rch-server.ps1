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

Write-Host "Installed RCH Rust server to $InstallDir"
Write-Host "Start with: $InstallDir\packaging\windows\start-rch-server.ps1"
