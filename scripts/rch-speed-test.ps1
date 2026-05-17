param(
    [string] $BaseUrl = "http://127.0.0.1:8081",
    [string] $ApiKey = "manual-test",
    [int] $Iterations = 40,
    [int] $Warmup = 5,
    [switch] $IncludeWrites,
    [string] $MissionUid = "sar-spruce-ridge-2026",
    [string] $OutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

if ($Iterations -lt 1) {
    throw "Iterations must be at least 1."
}
if ($Warmup -lt 0) {
    throw "Warmup must not be negative."
}

Add-Type -AssemblyName System.Net.Http

$base = $BaseUrl.TrimEnd("/")
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(60)
if (-not [string]::IsNullOrWhiteSpace($ApiKey)) {
    $client.DefaultRequestHeaders.Add("X-API-Key", $ApiKey)
}

function New-Request {
    param(
        [Parameter(Mandatory = $true)] [string] $Method,
        [Parameter(Mandatory = $true)] [string] $Path,
        [object] $Body = $null
    )

    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method),
        "$base$Path"
    )
    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 20 -Compress
        $request.Content = [System.Net.Http.StringContent]::new(
            $json,
            [System.Text.Encoding]::UTF8,
            "application/json"
        )
    }
    return $request
}

function Invoke-MeasuredRequest {
    param(
        [Parameter(Mandatory = $true)] [string] $Method,
        [Parameter(Mandatory = $true)] [string] $Path,
        [object] $Body = $null
    )

    $request = New-Request -Method $Method -Path $Path -Body $Body
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $bytes = 0
        if ($null -ne $response.Content) {
            $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult().Length
        }
        $timer.Stop()
        return [pscustomobject]@{
            ok = $response.IsSuccessStatusCode
            status = [int] $response.StatusCode
            elapsed_ms = [math]::Round($timer.Elapsed.TotalMilliseconds, 3)
            bytes = $bytes
            error = ""
        }
    } catch {
        $timer.Stop()
        return [pscustomobject]@{
            ok = $false
            status = 0
            elapsed_ms = [math]::Round($timer.Elapsed.TotalMilliseconds, 3)
            bytes = 0
            error = $_.Exception.Message
        }
    } finally {
        $request.Dispose()
    }
}

function Get-Percentile {
    param(
        [double[]] $Values,
        [Parameter(Mandatory = $true)] [double] $Percentile
    )

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return $null
    }
    $sorted = @($Values | Sort-Object)
    $index = [math]::Ceiling(($Percentile / 100.0) * $sorted.Count) - 1
    if ($index -lt 0) {
        $index = 0
    }
    if ($index -ge $sorted.Count) {
        $index = $sorted.Count - 1
    }
    return [math]::Round([double] $sorted[$index], 3)
}

function Measure-Endpoint {
    param(
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [string] $Method,
        [Parameter(Mandatory = $true)] [string] $Path,
        [object] $Body = $null
    )

    for ($i = 0; $i -lt $Warmup; $i++) {
        Invoke-MeasuredRequest -Method $Method -Path $Path -Body $Body | Out-Null
    }

    $samples = New-Object System.Collections.Generic.List[object]
    for ($i = 0; $i -lt $Iterations; $i++) {
        $samples.Add((Invoke-MeasuredRequest -Method $Method -Path $Path -Body $Body))
    }

    $successes = @($samples | Where-Object { $_.ok })
    $failures = @($samples | Where-Object { -not $_.ok })
    $latencies = [double[]] @($successes | ForEach-Object { [double] $_.elapsed_ms })
    $bytes = @($successes | Select-Object -ExpandProperty bytes)
    $avg = if ($latencies.Count -gt 0) {
        [math]::Round(($latencies | Measure-Object -Average).Average, 3)
    } else {
        $null
    }

    return [pscustomobject]@{
        name = $Name
        method = $Method
        path = $Path
        iterations = $Iterations
        warmup = $Warmup
        success = $successes.Count
        failures = $failures.Count
        status_codes = @($samples | Group-Object status | ForEach-Object {
            [pscustomobject]@{ status = [int] $_.Name; count = $_.Count }
        })
        bytes_min = if ($bytes.Count -gt 0) { ($bytes | Measure-Object -Minimum).Minimum } else { $null }
        bytes_max = if ($bytes.Count -gt 0) { ($bytes | Measure-Object -Maximum).Maximum } else { $null }
        min_ms = Get-Percentile -Values $latencies -Percentile 0
        avg_ms = $avg
        p50_ms = Get-Percentile -Values $latencies -Percentile 50
        p95_ms = Get-Percentile -Values $latencies -Percentile 95
        p99_ms = Get-Percentile -Values $latencies -Percentile 99
        max_ms = Get-Percentile -Values $latencies -Percentile 100
        first_error = if ($failures.Count -gt 0) { $failures[0].error } else { "" }
    }
}

$tests = @(
    @{ name = "status"; method = "GET"; path = "/Status" },
    @{ name = "runtime-diagnostics"; method = "GET"; path = "/diagnostics/runtime" },
    @{ name = "app-info"; method = "GET"; path = "/api/v1/app/info" },
    @{ name = "events"; method = "GET"; path = "/Events" },
    @{ name = "telemetry"; method = "GET"; path = "/Telemetry?since=0" },
    @{ name = "clients"; method = "GET"; path = "/Client" },
    @{ name = "identities"; method = "GET"; path = "/Identities" },
    @{ name = "rem-peers"; method = "GET"; path = "/api/rem/peers" },
    @{ name = "topics"; method = "GET"; path = "/Topic" },
    @{ name = "subscribers"; method = "GET"; path = "/Subscriber" },
    @{ name = "files"; method = "GET"; path = "/File" },
    @{ name = "images"; method = "GET"; path = "/Image" },
    @{ name = "chat-messages"; method = "GET"; path = "/Chat/Messages" },
    @{ name = "markers"; method = "GET"; path = "/api/markers" },
    @{ name = "zones"; method = "GET"; path = "/api/zones" },
    @{ name = "checklists"; method = "GET"; path = "/checklists" },
    @{ name = "checklist-templates"; method = "GET"; path = "/checklists/templates" },
    @{ name = "eam"; method = "GET"; path = "/api/EmergencyActionMessage" },
    @{ name = "missions"; method = "GET"; path = "/api/r3akt/missions" },
    @{ name = "mission-expanded"; method = "GET"; path = "/api/r3akt/missions/$MissionUid`?expand=all" },
    @{ name = "mission-log-entries"; method = "GET"; path = "/api/r3akt/log-entries`?mission_uid=$MissionUid" },
    @{ name = "mission-changes"; method = "GET"; path = "/api/r3akt/mission-changes`?include_delta=false" },
    @{ name = "teams"; method = "GET"; path = "/api/r3akt/teams" },
    @{ name = "team-members"; method = "GET"; path = "/api/r3akt/team-members" },
    @{ name = "assets"; method = "GET"; path = "/api/r3akt/assets" },
    @{ name = "assignments"; method = "GET"; path = "/api/r3akt/assignments" },
    @{ name = "r3akt-events"; method = "GET"; path = "/api/r3akt/events`?limit=25&include_payload=false" },
    @{ name = "r3akt-snapshots"; method = "GET"; path = "/api/r3akt/snapshots" }
)

if ($IncludeWrites) {
    $tests += @{
        name = "log-entry-upsert"
        method = "POST"
        path = "/api/r3akt/log-entries"
        body = @{
            entry_uid = "rch-speed-test-log-entry"
            mission_uid = $MissionUid
            callsign = "RCH-PERF"
            content = "RCH speed-test log upsert"
            keywords = @("perf", "speed-test")
        }
    }
}

$startedAt = (Get-Date).ToString("o")
$results = New-Object System.Collections.Generic.List[object]
foreach ($test in $tests) {
    $body = if ($test.ContainsKey("body")) { $test.body } else { $null }
    $result = Measure-Endpoint `
        -Name $test.name `
        -Method $test.method `
        -Path $test.path `
        -Body $body
    $results.Add($result)
    Write-Host ("{0,-24} {1,4} {2,8} ok={3}/{4} avg={5,8}ms p95={6,8}ms max={7,8}ms" -f `
        $result.name,
        $result.method,
        $result.path,
        $result.success,
        $result.iterations,
        $result.avg_ms,
        $result.p95_ms,
        $result.max_ms
    )
}

$report = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    started_at = $startedAt
    base_url = $base
    iterations = $Iterations
    warmup = $Warmup
    include_writes = [bool] $IncludeWrites
    mission_uid = $MissionUid
    results = $results
}

if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $parent = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $report | ConvertTo-Json -Depth 20 | Set-Content -Path $OutputPath -Encoding utf8
}

$report
