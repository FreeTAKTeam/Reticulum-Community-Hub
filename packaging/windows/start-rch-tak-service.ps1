param(
    [string] $InstallDir = "$PSScriptRoot\..",
    [string] $RchBaseUrl = "http://127.0.0.1:8000",
    [string] $RchApiKey = "change-me",
    [string] $CotUrl = "tcp://127.0.0.1:8087",
    [double] $IntervalSeconds = 5,
    [switch] $RchToTakOnly,
    [switch] $TakToRchOnly
)

$ErrorActionPreference = "Stop"
$bin = Join-Path $InstallDir "bin\r3akt-tak-service.exe"

$serviceArgs = @(
    "--rch-base-url", $RchBaseUrl,
    "--tak-cot-url", $CotUrl,
    "--interval-seconds", "$IntervalSeconds"
)

if ($RchApiKey) {
    $serviceArgs += @("--rch-api-key", $RchApiKey)
}

if ($RchToTakOnly -and $TakToRchOnly) {
    throw "Choose only one of -RchToTakOnly or -TakToRchOnly."
}

if ($RchToTakOnly) {
    $serviceArgs += "--rch-to-tak-only"
}

if ($TakToRchOnly) {
    $serviceArgs += "--tak-to-rch-only"
}

& $bin @serviceArgs
