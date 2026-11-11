$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$helper = Join-Path $PSScriptRoot "attach-release-assets.ps1"
$testDir = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) "rch-release-assets-$([guid]::NewGuid())")
$arguments = @{ Repository = "owner/repo"; Tag = "v3.0.0-preview.38"; Path = "$($testDir.FullName)/*.zip" }

$state = [pscustomobject]@{
    Calls = [Collections.Generic.List[string]]::new()
    ViewExit = 0
    UploadExit = 0
    Assets = @()
}

${function:gh} = {
    $state.Calls.Add(($args -join " "))
    switch ($args[1]) {
        "view" {
            $global:LASTEXITCODE = $state.ViewExit
            if ($state.ViewExit -eq 0) {
                @{ assets = $state.Assets } | ConvertTo-Json -Compress
            }
        }
        "upload" { $global:LASTEXITCODE = $state.UploadExit }
        default { throw "Unexpected gh operation: $args" }
    }
}.GetNewClosure()

function Assert-Fails {
    param([string] $Message, [switch] $VerifyOnly)
    try {
        & $helper @arguments -VerifyOnly:$VerifyOnly
    } catch {
        if ($_.Exception.Message -notlike $Message) { throw }
        return
    }
    throw "Expected failure: $Message"
}

$originalExitCode = Get-Variable -Name LASTEXITCODE -Scope Global -ValueOnly -ErrorAction SilentlyContinue
try {
    $package = New-Item -ItemType File -Path (Join-Path $testDir.FullName "package.zip")
    $desktop = New-Item -ItemType File -Path (Join-Path $testDir.FullName "desktop build.zip")
    $view = "release view --repo owner/repo --json assets -- v3.0.0-preview.38"
    $upload = "release upload --repo owner/repo -- v3.0.0-preview.38 $($desktop.FullName)"
    $state.Assets = @(
        @{ name = $package.Name; label = "" },
        @{ name = "desktop.build.zip"; label = $desktop.Name }
    )

    & $helper @arguments
    if ($state.Calls.Count -ne 1 -or $state.Calls[0] -ne $view) { throw "Existing names and labels must only be read." }

    $state.Calls.Clear()
    $state.Assets = @($state.Assets[0])
    & $helper @arguments
    if ($state.Calls.Count -ne 2 -or $state.Calls[0] -ne $view -or $state.Calls[1] -ne $upload) {
        throw "Only the missing package should be uploaded."
    }

    $state.Calls.Clear()
    $arguments.Tag = "--clobber"
    & $helper @arguments
    if ($state.Calls.Count -ne 2 -or
        $state.Calls[0] -ne "release view --repo owner/repo --json assets -- --clobber" -or
        $state.Calls[1] -ne "release upload --repo owner/repo -- --clobber $($desktop.FullName)") {
        throw "A flag-like tag must follow the option terminator."
    }
    $arguments.Tag = "v3.0.0-preview.38"

    $state.Calls.Clear()
    Assert-Fails "Missing release assets:*" -VerifyOnly
    if ($state.Calls.Count -ne 1 -or $state.Calls[0] -ne $view) { throw "VerifyOnly must never upload." }

    $state.Calls.Clear()
    $state.ViewExit = 1
    Assert-Fails "Failed to list assets*"
    if ($state.Calls.Count -ne 1 -or $state.Calls[0] -ne $view) { throw "A listing failure must stop the upload." }

    $state.Calls.Clear()
    $state.ViewExit = 0
    $state.UploadExit = 1
    Assert-Fails "Failed to upload missing assets*"
    if ($state.Calls.Count -ne 2 -or $state.Calls[1] -ne $upload) { throw "An upload failure must be reported." }

    $state.Calls.Clear()
    $arguments.Path = "$($testDir.FullName)/*.deb"
    Assert-Fails "No release assets match*"
    if ($state.Calls.Count -ne 0) { throw "A missing local asset must fail before contacting GitHub." }

    Write-Host "Release asset attachment tests passed."
} finally {
    if ($null -eq $originalExitCode) {
        Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    } else {
        $global:LASTEXITCODE = $originalExitCode
    }
    Remove-Item -LiteralPath $testDir.FullName -Recurse -Force
}
