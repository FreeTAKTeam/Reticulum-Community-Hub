param(
    [string]$ReticulumdExe = (Join-Path (Resolve-Path "..\LXMF-rs\target\debug").Path "reticulumd.exe"),
    [string]$ExternalConfigPath = "",
    [string]$RustToolchain = "1.85.0",
    [int]$NodeCount = 3,
    [int]$TimeoutSeconds = 90,
    [int]$DiscoverySettleSeconds = 3,
    [int]$ReceiptPollAttempts = 120,
    [int]$ReceiptPollDelayMs = 500,
    [switch]$IncludeZmqEventPoll
)

$ErrorActionPreference = "Stop"

if ($NodeCount -lt 3) {
    throw "NodeCount must be at least 3 for direct receipt plus two-recipient fanout validation."
}

if (-not (Test-Path -LiteralPath $ReticulumdExe)) {
    throw "reticulumd executable not found: $ReticulumdExe"
}

if (-not [string]::IsNullOrWhiteSpace($ExternalConfigPath)) {
    $ExternalConfigPath = (Resolve-Path -LiteralPath $ExternalConfigPath).Path
    if ($DiscoverySettleSeconds -lt 30) {
        $DiscoverySettleSeconds = 30
    }
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
$savedEnv = @{
    R3AKT_RETICULUMD_RPC_ENDPOINT = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_RPC_ENDPOINT")
    R3AKT_RETICULUMD_SOURCE = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_SOURCE")
    R3AKT_RETICULUMD_RECEIPT_DESTINATION = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_RECEIPT_DESTINATION")
    R3AKT_RETICULUMD_FANOUT_DESTINATIONS = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_FANOUT_DESTINATIONS")
    R3AKT_RETICULUMD_RECEIPT_POLL_ATTEMPTS = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_RECEIPT_POLL_ATTEMPTS")
    R3AKT_RETICULUMD_RECEIPT_POLL_DELAY_MS = [Environment]::GetEnvironmentVariable("R3AKT_RETICULUMD_RECEIPT_POLL_DELAY_MS")
    R3AKT_LXMF_ZMQ_COMMAND_ENDPOINT = [Environment]::GetEnvironmentVariable("R3AKT_LXMF_ZMQ_COMMAND_ENDPOINT")
    R3AKT_LXMF_ZMQ_RESPONSE_ENDPOINT = [Environment]::GetEnvironmentVariable("R3AKT_LXMF_ZMQ_RESPONSE_ENDPOINT")
    R3AKT_ENABLE_ZMQ_EVENT_POLL = [Environment]::GetEnvironmentVariable("R3AKT_ENABLE_ZMQ_EVENT_POLL")
}

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null

    $rpcPorts = @()
    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $rpcPorts += Get-FreeTcpPort
    }
    $transportPorts = @()
    if ([string]::IsNullOrWhiteSpace($ExternalConfigPath)) {
        for ($idx = 0; $idx -lt $NodeCount; $idx++) {
            $transportPorts += Get-FreeTcpPort
        }
    }
    $zmqCommandEndpoint = $null
    $zmqResponseEndpoint = $null
    if ($IncludeZmqEventPoll) {
        $zmqCommandEndpoint = "tcp://127.0.0.1:$(Get-FreeTcpPort)"
        $zmqResponseEndpoint = "tcp://127.0.0.1:$(Get-FreeTcpPort)"
    }

    for ($idx = 0; $idx -lt $NodeCount; $idx++) {
        $nodeDir = Join-Path $tempRoot "node-$idx"
        New-Item -ItemType Directory -Path $nodeDir | Out-Null
        $configPath = Join-Path $nodeDir "reticulum.toml"
        if ([string]::IsNullOrWhiteSpace($ExternalConfigPath)) {
            Write-NodeConfig -Path $configPath -NodeIndex $idx -TransportPorts $transportPorts
        } else {
            Copy-Item -LiteralPath $ExternalConfigPath -Destination $configPath
        }

        $stdoutPath = Join-Path $nodeDir "reticulumd.out.log"
        $stderrPath = Join-Path $nodeDir "reticulumd.err.log"
        $args = @(
            "--rpc", "127.0.0.1:$($rpcPorts[$idx])",
            "--db", (Join-Path $nodeDir "reticulum.db"),
            "--announce-interval-secs", "1"
        )
        if ([string]::IsNullOrWhiteSpace($ExternalConfigPath)) {
            $args += @("--transport", "127.0.0.1:$($transportPorts[$idx])")
        }
        if ($IncludeZmqEventPoll -and $idx -eq 0) {
            $args += @("--zmq-rpc-command", $zmqCommandEndpoint)
        }
        $args += @("--config", $configPath)
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
    if ($IncludeZmqEventPoll) {
        Write-Host "  node-0 zmq-command=$zmqCommandEndpoint zmq-response=$zmqResponseEndpoint"
    }

    Start-Sleep -Seconds $DiscoverySettleSeconds

    $env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:$($rpcPorts[0])"
    $env:R3AKT_RETICULUMD_SOURCE = $destinations[0]
    $env:R3AKT_RETICULUMD_RECEIPT_DESTINATION = $destinations[1]
    $env:R3AKT_RETICULUMD_FANOUT_DESTINATIONS = ($destinations[1..($NodeCount - 1)] -join ",")
    $env:R3AKT_RETICULUMD_RECEIPT_POLL_ATTEMPTS = "$ReceiptPollAttempts"
    $env:R3AKT_RETICULUMD_RECEIPT_POLL_DELAY_MS = "$ReceiptPollDelayMs"
    if ($IncludeZmqEventPoll) {
        $env:R3AKT_LXMF_ZMQ_COMMAND_ENDPOINT = $zmqCommandEndpoint
        $env:R3AKT_LXMF_ZMQ_RESPONSE_ENDPOINT = $zmqResponseEndpoint
        $env:R3AKT_ENABLE_ZMQ_EVENT_POLL = "1"
    }

    cargo "+$RustToolchain" test -p r3akt-rch-server live_reticulumd_direct_send_receipt_is_delivered_when_configured -- --nocapture
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    cargo "+$RustToolchain" test -p r3akt-rch-server live_reticulumd_topic_fanout_receipts_are_delivered_when_configured -- --nocapture
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    if ($IncludeZmqEventPoll) {
        cargo "+$RustToolchain" test -p r3akt-rch-server live_reticulumd_zmq_event_poll_succeeds_when_configured -- --nocapture
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
} finally {
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($name in $savedEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnv[$name])
    }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
