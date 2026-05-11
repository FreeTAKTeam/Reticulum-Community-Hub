param(
    [string]$ReticulumdExe = (Join-Path (Resolve-Path "..\LXMF-rs\target\debug").Path "reticulumd.exe"),
    [string]$RustToolchain = "1.85.0",
    [int]$NodeCount = 3,
    [int]$TimeoutSeconds = 90,
    [int]$ReceiptPollAttempts = 120,
    [int]$ReceiptPollDelayMs = 500
)

$ErrorActionPreference = "Stop"

if ($NodeCount -lt 3) {
    throw "NodeCount must be at least 3 for direct receipt plus two-recipient fanout validation."
}

if (-not (Test-Path -LiteralPath $ReticulumdExe)) {
    throw "reticulumd executable not found: $ReticulumdExe"
}

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

function Wait-ForDeliveryHash {
    param(
        [string]$StdoutPath,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $StdoutPath) {
            $content = Get-Content -LiteralPath $StdoutPath -ErrorAction SilentlyContinue
            foreach ($line in $content) {
                if ($line -match "delivery destination hash=([0-9a-fA-F]+)") {
                    return $Matches[1]
                }
            }
        }
        Start-Sleep -Milliseconds 250
    }

    throw "Timed out waiting for delivery destination hash in $StdoutPath"
}

function Write-NodeConfig {
    param(
        [string]$Path,
        [int]$NodeIndex,
        [int[]]$TransportPorts
    )

    $nodeCount = $TransportPorts.Count
    $next = ($NodeIndex + 1) % $nodeCount
    $previous = ($NodeIndex + $nodeCount - 1) % $nodeCount
    $neighbors = @($next)
    if ($previous -ne $next) {
        $neighbors += $previous
    }

    $config = New-Object System.Text.StringBuilder
    foreach ($neighbor in $neighbors) {
        [void]$config.AppendLine("[[interfaces]]")
        [void]$config.AppendLine('type = "tcp_client"')
        [void]$config.AppendLine("enabled = true")
        [void]$config.AppendLine('host = "127.0.0.1"')
        [void]$config.AppendLine("port = $($TransportPorts[$neighbor])")
        [void]$config.AppendLine()
    }
    Set-Content -LiteralPath $Path -Value $config.ToString() -Encoding utf8
}

$tempRoot = Join-Path $env:TEMP ("r3akt-local-reticulum-live-" + [guid]::NewGuid().ToString("N"))
$processes = @()

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null

    $rpcPorts = @()
    $transportPorts = @()
    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $rpcPorts += Get-FreeTcpPort
    }
    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $transportPorts += Get-FreeTcpPort
    }

    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $nodeDir = Join-Path $tempRoot "node-$idx"
        New-Item -ItemType Directory -Path $nodeDir | Out-Null
        $configPath = Join-Path $nodeDir "reticulum.toml"
        Write-NodeConfig -Path $configPath -NodeIndex $idx -TransportPorts $transportPorts

        $stdoutPath = Join-Path $nodeDir "reticulumd.out.log"
        $stderrPath = Join-Path $nodeDir "reticulumd.err.log"
        $args = @(
            "--rpc", "127.0.0.1:$($rpcPorts[$idx])",
            "--db", (Join-Path $nodeDir "reticulum.db"),
            "--announce-interval-secs", "1",
            "--transport", "127.0.0.1:$($transportPorts[$idx])",
            "--config", $configPath
        )
        $processes += Start-Process -FilePath $ReticulumdExe `
            -ArgumentList $args `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru
    }

    $destinations = @()
    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $stdoutPath = Join-Path (Join-Path $tempRoot "node-$idx") "reticulumd.out.log"
        $destinations += Wait-ForDeliveryHash -StdoutPath $stdoutPath -TimeoutSeconds $TimeoutSeconds
    }

    Write-Host "Local reticulumd nodes:"
    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        Write-Host "  node-$idx rpc=127.0.0.1:$($rpcPorts[$idx]) delivery=$($destinations[$idx])"
    }

    Start-Sleep -Seconds 3

    $env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:$($rpcPorts[0])"
    $env:R3AKT_RETICULUMD_SOURCE = $destinations[0]
    $env:R3AKT_RETICULUMD_RECEIPT_DESTINATION = $destinations[1]
    $env:R3AKT_RETICULUMD_FANOUT_DESTINATIONS = ($destinations[1..($NodeCount - 1)] -join ",")
    $env:R3AKT_RETICULUMD_RECEIPT_POLL_ATTEMPTS = "$ReceiptPollAttempts"
    $env:R3AKT_RETICULUMD_RECEIPT_POLL_DELAY_MS = "$ReceiptPollDelayMs"

    cargo "+$RustToolchain" test -p r3akt-rch-server live_reticulumd_direct_send_receipt_is_delivered_when_configured -- --nocapture
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    cargo "+$RustToolchain" test -p r3akt-rch-server live_reticulumd_topic_fanout_receipts_are_delivered_when_configured -- --nocapture
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
