$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$allowlist = @{}
Get-Content -LiteralPath "config/module-size-allowlist.txt" | ForEach-Object {
    $line = $_.Trim()
    if ($line.Length -eq 0 -or $line.StartsWith("#")) {
        return
    }
    $parts = $line.Split("|", 2)
    if ($parts.Count -ne 2) {
        throw "Invalid module size allowlist row: $line"
    }
    $allowlist[$parts[0]] = [int]$parts[1]
}

$failures = [System.Collections.Generic.List[string]]::new()
Get-ChildItem -LiteralPath "crates" -Recurse -Filter "*.rs" | ForEach-Object {
    $relative = $_.FullName.Substring((Get-Location).Path.Length + 1).Replace("\", "/")
    $sourceLines = @(Get-Content -LiteralPath $_.FullName)
    $cfgAttributeLines = 0
    $insideCfgAttribute = $false
    foreach ($sourceLine in $sourceLines) {
        if ($sourceLine.StartsWith("#![cfg_attr(")) {
            $insideCfgAttribute = $true
        }
        if ($insideCfgAttribute) {
            $cfgAttributeLines++
            if ($sourceLine.Trim() -eq ")]") {
                $insideCfgAttribute = $false
            }
        }
    }
    # Crate-level lint policy is enforcement metadata, not module body size.
    $lines = $sourceLines.Count - $cfgAttributeLines
    $isTest = $relative.Contains("/tests/") -or $_.Name.EndsWith("_test.rs") -or $_.Name.EndsWith("_tests.rs")
    $defaultLimit = if ($isTest) { 1200 } else { 500 }
    $limit = if ($allowlist.ContainsKey($relative)) { $allowlist[$relative] } else { $defaultLimit }
    if ($lines -gt $limit) {
        $failures.Add("$relative has $lines lines; limit is $limit")
    }
}

if ($failures.Count -gt 0) {
    throw "Rust module size budget failed:`n$($failures -join "`n")"
}

Write-Host "Rust module size budget passed."
