$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$root = (Get-Location).Path
$failures = [System.Collections.Generic.List[string]]::new()
$files = @(& git ls-files "*.md")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to enumerate tracked Markdown files."
}

foreach ($relativeFile in $files) {
    $file = Get-Item -LiteralPath (Join-Path $root $relativeFile)
    $content = Get-Content -LiteralPath $file.FullName -Raw
    $matches = [regex]::Matches($content, '!?(?<!\!)\[[^\]]*\]\((?<target>[^)]+)\)')
    foreach ($match in $matches) {
        $target = $match.Groups["target"].Value.Trim().Trim('<', '>')
        if ($target -match '^(?i:https?|mailto|ftp|data):' -or $target.StartsWith('#')) {
            continue
        }
        $target = ($target -split '#', 2)[0]
        $target = ($target -split '\?', 2)[0]
        if ([string]::IsNullOrWhiteSpace($target)) {
            continue
        }
        $target = [Uri]::UnescapeDataString($target)
        $candidate = if ($target.StartsWith('/')) {
            Join-Path $root $target.TrimStart('/')
        } else {
            Join-Path $file.DirectoryName $target
        }
        if (-not (Test-Path -LiteralPath $candidate)) {
            $failures.Add("${relativeFile}: missing local link target '$target'")
        }
    }
}

if ($failures.Count -gt 0) {
    throw "Documentation link validation failed:`n$($failures -join "`n")"
}

Write-Host "Documentation link validation passed for $($files.Count) tracked Markdown files."
