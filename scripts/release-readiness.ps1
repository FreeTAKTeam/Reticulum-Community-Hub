param(
    [switch] $ServerOnlyAlpha,
    [switch] $SkipUi,
    [switch] $SkipDesktop,
    [switch] $SkipClippy,
    [switch] $SkipWorkspaceTests,
    [switch] $SkipSmoke,
    [switch] $LiveTak,
    [switch] $LiveReticulum,
    [switch] $PlanOnly,
    [string] $Bind = "127.0.0.1:18080",
    [string] $ApiKey = "release-smoke",
    [string] $LxmfZmqCommand = "tcp://localhost:9100",
    [string] $LxmfZmqResponse = "tcp://localhost:9101",
    [string] $ReticulumdSource = "release-smoke-source"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Test-Windows {
    return [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)] [string] $FilePath,
        [Parameter(Mandatory = $true)] [string[]] $Arguments,
        [string] $WorkingDirectory = (Get-Location).Path
    )

    $display = "$FilePath $($Arguments -join ' ')"
    if ($PlanOnly) {
        Write-Host "PLAN: $display"
        return
    }

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $display"
        }
    } finally {
        Pop-Location
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [scriptblock] $Script
    )

    Write-Host ""
    Write-Host "==> $Name"
    & $Script
}

function Invoke-RustFormatCheck {
    if ($ServerOnlyAlpha) {
        Invoke-Native cargo @(
            "fmt",
            "-p", "r3akt-rch-server",
            "-p", "r3akt-rch-core",
            "-p", "r3akt-transport-rns",
            "-p", "r3akt-tak-connector",
            "--",
            "--check"
        )
    } else {
        Invoke-Native cargo @("fmt", "--all", "--", "--check")
    }
}

function Get-RequiredEnv {
    param([Parameter(Mandatory = $true)] [string] $Name)

    if ($PlanOnly) {
        Write-Host "PLAN: require environment variable $Name"
        return "<$Name>"
    }

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name must be set for this live release gate."
    }
    return $value
}

function Get-ReleaseBinary {
    param([Parameter(Mandatory = $true)] [string] $Name)

    $suffix = ""
    if (Test-Windows) {
        $suffix = ".exe"
    }
    return [System.IO.Path]::Combine((Get-Location).Path, "target", "release", "$Name$suffix")
}

function Invoke-ServerSmoke {
    if ($PlanOnly) {
        if ($ServerOnlyAlpha) {
            Write-Host "PLAN: start target/release/r3akt-rch-server with mandatory ZeroMQ SDK endpoints and validate /Status, /openapi.json, /Help, /api/v1/app/info, /diagnostics/runtime"
        } else {
            Write-Host "PLAN: start target/release/r3akt-rch-server and validate /Status, /openapi.json, /Help, /api/v1/app/info"
        }
        return
    }

    $serverBin = Get-ReleaseBinary "r3akt-rch-server"
    if (-not (Test-Path $serverBin)) {
        throw "Expected release server binary at $serverBin"
    }

    $db = Join-Path ([System.IO.Path]::GetTempPath()) ("r3akt-rch-release-smoke-" + [guid]::NewGuid().ToString() + ".sqlite3")
    $headers = @{ "X-API-Key" = $ApiKey }
    $serverArgs = @("--bind", $Bind, "--api-key", $ApiKey, "--db-path", $db)
    if ($ServerOnlyAlpha) {
        $serverArgs += @(
            "--lxmf-zmq-command", $LxmfZmqCommand,
            "--lxmf-zmq-response", $LxmfZmqResponse,
            "--reticulumd-source", $ReticulumdSource
        )
    }

    $startArgs = @{
        FilePath = $serverBin
        ArgumentList = $serverArgs
        WorkingDirectory = (Get-Location).Path
        PassThru = $true
    }
    if (Test-Windows) {
        $startArgs.WindowStyle = "Hidden"
    }
    $process = Start-Process @startArgs

    try {
        $baseUrl = "http://$Bind"
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            try {
                Invoke-RestMethod -Headers $headers -Uri "$baseUrl/Status" | Out-Null
                $ready = $true
                break
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }
        if (-not $ready) {
            throw "Server did not become ready at $baseUrl"
        }

        Invoke-RestMethod -Headers $headers -Uri "$baseUrl/Status" | Out-Null
        Invoke-RestMethod -Headers $headers -Uri "$baseUrl/openapi.json" | Out-Null
        Invoke-RestMethod -Headers $headers -Uri "$baseUrl/Help" | Out-Null
        Invoke-RestMethod -Headers $headers -Uri "$baseUrl/api/v1/app/info" | Out-Null
        if ($ServerOnlyAlpha) {
            $diagnostics = Invoke-RestMethod -Headers $headers -Uri "$baseUrl/diagnostics/runtime"
            if (-not $diagnostics.reticulumd_source_configured) {
                throw "Server-only alpha smoke expected a configured Reticulum source for mandatory ZeroMQ."
            }
        }
    } finally {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $db -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Step "Rust formatting" {
    Invoke-RustFormatCheck
}

if (-not $SkipClippy) {
    Invoke-Step "Rust clippy" {
        Invoke-Native cargo @("clippy", "--workspace", "--all-targets", "--", "-D", "warnings")
    }
}

if (-not $SkipWorkspaceTests) {
    Invoke-Step "Rust workspace tests" {
        Invoke-Native cargo @("test", "--workspace", "--", "--test-threads=1")
    }
}

Invoke-Step "Build RCH server release binary" {
    Invoke-Native cargo @("build", "--release", "-p", "r3akt-rch-server")
}

if (-not $ServerOnlyAlpha) {
    Invoke-Step "Build standalone TAK service release binary" {
        Invoke-Native cargo @("build", "--release", "-p", "r3akt-tak-connector", "--bin", "r3akt-tak-service")
    }
}

if (-not $SkipUi -and -not $ServerOnlyAlpha) {
    Invoke-Step "Shared UI install" {
        Invoke-Native npm @("--prefix", "ui", "ci")
    }
    Invoke-Step "Shared UI lint" {
        Invoke-Native npm @("--prefix", "ui", "run", "lint")
    }
    Invoke-Step "Shared UI tests" {
        Invoke-Native npm @("--prefix", "ui", "run", "test")
    }
    Invoke-Step "Shared UI build" {
        Invoke-Native npm @("--prefix", "ui", "run", "build")
    }
}

if (-not $SkipDesktop -and -not $ServerOnlyAlpha) {
    Invoke-Step "Desktop sidecar preparation" {
        Invoke-Native npm @("--prefix", "apps/rch-desktop", "run", "prepare:sidecar")
    }
}

if (-not $SkipSmoke) {
    Invoke-Step "Release server HTTP smoke" {
        Invoke-ServerSmoke
    }
}

if ($LiveTak) {
    Invoke-Step "Live TAK send/receive gates" {
        Get-RequiredEnv "R3AKT_TAK_LIVE_COT_URL" | Out-Null
        Get-RequiredEnv "R3AKT_TAK_LIVE_INBOUND_COT_URL" | Out-Null
        Invoke-Native cargo @("test", "-p", "r3akt-tak-connector", "live_tak_server_accepts_keepalive_when_configured", "--", "--nocapture")
        Invoke-Native cargo @("test", "-p", "r3akt-tak-connector", "live_tak_server_accepts_reconnect_when_configured", "--", "--nocapture")
        Invoke-Native cargo @("test", "-p", "r3akt-tak-connector", "live_tak_server_provides_inbound_cot_when_configured", "--", "--nocapture")
    }
}

if ($LiveReticulum) {
    Invoke-Step "Live Reticulum receipt/fanout gates" {
        Get-RequiredEnv "R3AKT_RETICULUMD_RPC_ENDPOINT" | Out-Null
        Get-RequiredEnv "R3AKT_RETICULUMD_SOURCE" | Out-Null
        Get-RequiredEnv "R3AKT_RETICULUMD_RECEIPT_DESTINATION" | Out-Null
        Get-RequiredEnv "R3AKT_RETICULUMD_FANOUT_DESTINATIONS" | Out-Null
        Invoke-Native cargo @("test", "-p", "r3akt-rch-server", "live_reticulumd_direct_send_receipt_is_delivered_when_configured", "--", "--nocapture")
        Invoke-Native cargo @("test", "-p", "r3akt-rch-server", "live_reticulumd_topic_fanout_receipts_are_delivered_when_configured", "--", "--nocapture")
    }
}

Write-Host ""
Write-Host "Release readiness checks completed."
