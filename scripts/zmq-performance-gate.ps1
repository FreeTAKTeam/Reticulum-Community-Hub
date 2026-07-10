$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$baseline = Get-Content -LiteralPath "config/zmq-performance-baseline.json" -Raw | ConvertFrom-Json
$savedPreference = $ErrorActionPreference
try {
    # Windows PowerShell promotes Cargo's normal stderr progress to a
    # NativeCommandError while Stop is active. Judge the gate by Cargo's exit
    # code and retain the combined stream for extracting the benchmark result.
    $ErrorActionPreference = "Continue"
    $output = cargo test --release -p r3akt-transport-rns lxmf_zmq_outbound_ten_thousand_batched_messages_complete -- --nocapture --test-threads=1 2>&1
    $cargoExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $savedPreference
}
if ($cargoExit -ne 0) {
    throw "ZMQ performance test failed:`n$($output -join "`n")"
}
$result = $output | Select-String -Pattern "messages_per_sec=([0-9.]+)" | Select-Object -Last 1
if (-not $result) {
    throw "ZMQ performance result did not report messages_per_sec"
}
$actual = [double]$result.Matches[0].Groups[1].Value
$minimum = [double]$baseline.minimum_messages_per_second
if ($actual -lt $minimum) {
    throw "ZMQ throughput regression: $actual messages/sec is below the 5% floor $minimum"
}

[pscustomobject]@{
    baseline_messages_per_second = [double]$baseline.messages_per_second
    baseline_workload = [string]$baseline.workload
    minimum_messages_per_second = $minimum
    actual_messages_per_second = $actual
    current_workload = "10_x_1000_recipient_sdk_batches"
    non_regression_comparable = [bool]$baseline.comparable_to_batched_projection
    status = "projection_floor_passed"
} | ConvertTo-Json -Compress
