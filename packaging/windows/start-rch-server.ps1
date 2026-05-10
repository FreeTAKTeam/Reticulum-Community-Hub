param(
    [string] $InstallDir = "$PSScriptRoot\..",
    [string] $Bind = "127.0.0.1:8000",
    [string] $DataDir = "$env:LOCALAPPDATA\RCH",
    [string] $ApiKey = "change-me"
)

$ErrorActionPreference = "Stop"
$bin = Join-Path $InstallDir "bin\r3akt-rch-server.exe"
$ui = Join-Path $InstallDir "ui"
$db = Join-Path $DataDir "rch_state.sqlite3"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:RTH_API_KEY = $ApiKey

& $bin --bind $Bind --db-path $db --ui-dist-path $ui
