param(
    [string] $InstallDir = "$PSScriptRoot\..\..",
    [string] $Bind = "127.0.0.1:8000",
    [string] $DataDir = "$env:LOCALAPPDATA\RCH",
    [string] $ApiKey = "change-me",
    [string] $LxmfZmqCommand = "tcp://localhost:9100",
    [string] $LxmfZmqResponse = "tcp://localhost:9101",
    [string] $ReticulumdSource = "change-me"
)

$ErrorActionPreference = "Stop"
$bin = Join-Path $InstallDir "bin\r3akt-rch-server.exe"
$ui = Join-Path $InstallDir "ui"
$db = Join-Path $DataDir "rch_state.sqlite3"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$env:RTH_API_KEY = $ApiKey

$args = @(
    "--bind", $Bind,
    "--db-path", $db,
    "--lxmf-zmq-command", $LxmfZmqCommand,
    "--lxmf-zmq-response", $LxmfZmqResponse,
    "--reticulumd-source", $ReticulumdSource
)

if (Test-Path $ui) {
    $args += @("--ui-dist-path", $ui)
}

& $bin @args
