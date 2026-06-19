param(
    [string]$MatrixPath = "docs/release-contract-matrix.json",
    [string]$OutputPath = "docs/release-parity-report.md",
    [string]$RustBaseUrl = "",
    [string]$PythonBaseUrl = "",
    [string]$ApiKey = "secret"
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
    $global:PSNativeCommandUseErrorActionPreference = $false
}

function Get-GitValue {
    param([string[]]$CommandArgs)
    try {
        $value = & git @CommandArgs 2>$null
        if ($LASTEXITCODE -eq 0) {
            return ($value -join "`n").Trim()
        }
    } catch {
        return ""
    }
    return ""
}

function Get-OpenApi {
    param([string]$BaseUrl)
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
        return $null
    }
    $uri = $BaseUrl.TrimEnd("/") + "/openapi.json"
    try {
        $response = & curl.exe --silent --show-error --max-time 30 -H "X-API-Key: $ApiKey" $uri 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw ($response -join "`n")
        }
        $content = $response -join "`n"
        $tempFile = [System.IO.Path]::GetTempFileName()
        $parserFile = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".py")
        try {
            Set-Content -Path $tempFile -Value $content -Encoding utf8
            $pythonScript = @'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8-sig") as handle:
    data = json.load(handle)

for path, operations in data.get("paths", {}).items():
    if isinstance(operations, dict):
        print(path + "\t" + ",".join(operations.keys()))
    else:
        print(path + "\t")
'@
            Set-Content -Path $parserFile -Value $pythonScript -Encoding utf8
            $routeLines = & python $parserFile $tempFile 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw ($routeLines -join "`n")
            }
            $routeIndex = New-Object System.Collections.Hashtable ([System.StringComparer]::Ordinal)
            foreach ($line in $routeLines) {
                $parts = $line -split "`t", 2
                if ($parts.Count -lt 1 -or [string]::IsNullOrWhiteSpace($parts[0])) {
                    continue
                }
                $methods = New-Object System.Collections.Hashtable ([System.StringComparer]::OrdinalIgnoreCase)
                if ($parts.Count -gt 1 -and -not [string]::IsNullOrWhiteSpace($parts[1])) {
                    foreach ($method in ($parts[1] -split ",")) {
                        if (-not [string]::IsNullOrWhiteSpace($method)) {
                            $methods[$method] = $true
                        }
                    }
                }
                $routeIndex[$parts[0]] = $methods
            }
            return [pscustomobject]@{
                route_index = $routeIndex
                uri = $uri
            }
        } finally {
            Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $parserFile -Force -ErrorAction SilentlyContinue
        }
    } catch {
        return [pscustomobject]@{
            error = $_.Exception.Message
            uri = $uri
        }
    }
}

function Test-OpenApiRoute {
    param(
        [object]$OpenApi,
        [string]$Path,
        [string]$Method
    )
    if ($null -eq $OpenApi) {
        return "not-run"
    }
    if ($OpenApi -is [System.Collections.IDictionary] -and $OpenApi.Contains("error")) {
        return "openapi-error"
    }
    if ($OpenApi.PSObject.Properties.Name -contains "error") {
        return "openapi-error"
    }
    if ($OpenApi.PSObject.Properties.Name -contains "route_index") {
        $routeIndex = $OpenApi.route_index
        if (-not $routeIndex.Contains($Path)) {
            return "missing-path"
        }
        if ($routeIndex[$Path].Contains($Method.ToLowerInvariant())) {
            return "pass"
        }
        return "missing-method"
    }
    $paths = if ($OpenApi -is [System.Collections.IDictionary]) {
        $OpenApi["paths"]
    } else {
        $OpenApi.paths
    }
    if ($null -eq $paths) {
        return "missing-path"
    }
    $operations = $null
    if ($paths -is [System.Collections.IDictionary]) {
        if (-not $paths.Contains($Path)) {
            return "missing-path"
        }
        $operations = $paths[$Path]
    } elseif ($paths.PSObject.Properties.Name -contains $Path) {
        $operations = $paths.PSObject.Properties[$Path].Value
    } else {
        return "missing-path"
    }

    $methodName = $Method.ToLowerInvariant()
    if ($operations -is [System.Collections.IDictionary]) {
        if ($operations.Contains($methodName)) {
            return "pass"
        }
    } elseif ($operations.PSObject.Properties.Name -contains $methodName) {
        return "pass"
    }
    return "missing-method"
}

function Get-ContractRoutes {
    param([object]$Contract)
    if ($null -ne $Contract.routes) {
        return @($Contract.routes)
    }
    if ($null -ne $Contract.path -and $null -ne $Contract.method) {
        return @([pscustomobject]@{ path = $Contract.path; method = $Contract.method })
    }
    return @()
}

$matrixFullPath = Join-Path (Get-Location) $MatrixPath
$matrix = Get-Content -Raw -Path $matrixFullPath | ConvertFrom-Json
$contracts = @($matrix.contracts)
$rustOpenApi = Get-OpenApi -BaseUrl $RustBaseUrl
$pythonOpenApi = Get-OpenApi -BaseUrl $PythonBaseUrl

$rustBranch = Get-GitValue -CommandArgs @("branch", "--show-current")
$rustCommit = Get-GitValue -CommandArgs @("rev-parse", "HEAD")
$pythonCommit = Get-GitValue -CommandArgs @("rev-parse", "rch-python")
$workspaceStatus = Get-GitValue -CommandArgs @("status", "--short")
$lxmfPath = Join-Path (Split-Path (Get-Location) -Parent) "LXMF-rs"
$lxmfCommit = ""
if (Test-Path $lxmfPath) {
    Push-Location $lxmfPath
    try {
        $lxmfCommit = Get-GitValue -CommandArgs @("rev-parse", "HEAD")
    } finally {
        Pop-Location
    }
}

$routeResults = New-Object System.Collections.Generic.List[object]
foreach ($contract in $contracts) {
    if ($contract.kind -ne "http-route") {
        continue
    }
    foreach ($route in Get-ContractRoutes $contract) {
        $routeResults.Add([pscustomobject]@{
            contract = $contract.id
            classification = $contract.classification
            method = $route.method.ToUpperInvariant()
            path = $route.path
            rust = Test-OpenApiRoute -OpenApi $rustOpenApi -Path $route.path -Method $route.method
            python = Test-OpenApiRoute -OpenApi $pythonOpenApi -Path $route.path -Method $route.method
        })
    }
}

$mustMatchContracts = @($contracts | Where-Object { $_.classification -eq "must-match-python" })
$rustAdditiveContracts = @($contracts | Where-Object { $_.classification -eq "rust-additive-required" })
$differenceContracts = @($contracts | Where-Object { $_.classification -eq "intentional-difference" })
$routeFailures = @($routeResults | Where-Object { $_.rust -notin @("pass", "not-run") })
$pythonRouteFailures = @($routeResults | Where-Object { $_.python -notin @("pass", "not-run") })

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# Python Parity Plus Rust Release Capability Report")
$lines.Add("")
$lines.Add("Generated: $(Get-Date -Format o)")
$lines.Add("")
$lines.Add("## Baselines")
$lines.Add("")
$lines.Add("- Python baseline branch: ``rch-python``")
$lines.Add(("- Python baseline commit: ``{0}``" -f $pythonCommit))
$lines.Add(("- Rust branch: ``{0}``" -f $rustBranch))
$lines.Add(("- Rust commit: ``{0}``" -f $rustCommit))
$lines.Add(("- LXMF-rs sibling commit: ``{0}``" -f $(if ($lxmfCommit) { $lxmfCommit } else { "not-found" })))
$lines.Add(("- Contract matrix: ``{0}``" -f $MatrixPath))
$lines.Add(("- Rust OpenAPI probe: ``{0}``" -f $(if ($RustBaseUrl) { $RustBaseUrl } else { "not-run" })))
$lines.Add(("- Python OpenAPI probe: ``{0}``" -f $(if ($PythonBaseUrl) { $PythonBaseUrl } else { "not-run" })))
$lines.Add("")
$lines.Add("## Decision Model")
$lines.Add("")
$lines.Add("- ``must-match-python``: Python public behavior that Rust must preserve.")
$lines.Add("- ``rust-additive-required``: Rust release capability that is mandatory even when Python lacks it.")
$lines.Add("- ``intentional-difference``: Documented architecture difference with equivalent or improved public behavior.")
$lines.Add("")
$lines.Add("## Contract Summary")
$lines.Add("")
$lines.Add("| Classification | Contracts | HTTP routes |")
$lines.Add("| --- | ---: | ---: |")
$lines.Add("| must-match-python | $($mustMatchContracts.Count) | $(@($routeResults | Where-Object { $_.classification -eq "must-match-python" }).Count) |")
$lines.Add("| rust-additive-required | $($rustAdditiveContracts.Count) | $(@($routeResults | Where-Object { $_.classification -eq "rust-additive-required" }).Count) |")
$lines.Add("| intentional-difference | $($differenceContracts.Count) | $(@($routeResults | Where-Object { $_.classification -eq "intentional-difference" }).Count) |")
$lines.Add("")
$lines.Add("## Python-Compatible Contracts")
$lines.Add("")
foreach ($contract in $mustMatchContracts) {
    $lines.Add(("- ``{0}`` ({1}): {2}" -f $contract.id, $contract.kind, $contract.description))
}
$lines.Add("")
$lines.Add("## Rust Additive Required Capabilities")
$lines.Add("")
foreach ($contract in $rustAdditiveContracts) {
    $lines.Add(("- ``{0}`` ({1}): {2}" -f $contract.id, $contract.kind, $contract.description))
}
$lines.Add("")
$lines.Add("## Intentional Differences")
$lines.Add("")
foreach ($contract in $differenceContracts) {
    $lines.Add(("- ``{0}`` ({1}): {2}" -f $contract.id, $contract.kind, $contract.description))
}
$lines.Add("")
$lines.Add("## HTTP Route Probe Results")
$lines.Add("")
if ($routeResults.Count -eq 0) {
    $lines.Add("No HTTP route contracts were present in the matrix.")
} else {
    $lines.Add("| Method | Path | Rust OpenAPI | Python OpenAPI |")
    $lines.Add("| --- | --- | --- | --- |")
    foreach ($result in $routeResults) {
        $lines.Add(("| ``{0}`` | ``{1}`` | {2} | {3} |" -f $result.method, $result.path, $result.rust, $result.python))
    }
}
$lines.Add("")
$lines.Add("## Release Decision Inputs")
$lines.Add("")
if ($routeFailures.Count -eq 0) {
    $lines.Add("- Rust OpenAPI has no failed route probes for the matrix scope.")
} else {
    $lines.Add("- Rust OpenAPI route probe failures: $($routeFailures.Count)")
}
if ($pythonRouteFailures.Count -eq 0) {
    $lines.Add("- Python OpenAPI has no failed route probes for the matrix scope.")
} else {
    $lines.Add("- Python OpenAPI route probe failures: $($pythonRouteFailures.Count)")
}
$lines.Add("- Rust additive capability gates must still be backed by their named evidence commands before final release.")
$lines.Add("- True Python-visible mismatches must be fixed or explicitly waived; Rust additive failures block release even without Python equivalents.")
$lines.Add("")
$lines.Add("## Workspace Status")
$lines.Add("")
if ([string]::IsNullOrWhiteSpace($workspaceStatus)) {
    $lines.Add('`git status --short` was clean when the report was generated.')
} else {
    $lines.Add('```text')
    $lines.Add($workspaceStatus)
    $lines.Add('```')
}

$outputFullPath = Join-Path (Get-Location) $OutputPath
$outputDir = Split-Path -Parent $outputFullPath
if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}
$lines | Set-Content -Path $outputFullPath -Encoding utf8
Write-Host "Wrote $OutputPath"
if ($routeFailures.Count -gt 0) {
    exit 1
}
