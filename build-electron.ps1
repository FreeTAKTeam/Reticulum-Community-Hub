<# 
Build Electron desktop artifacts for RCH.

Notes:
- Windows builds must run on Windows.
- macOS builds must run on macOS.
- Raspberry Pi OS 64-bit builds must run on Linux arm64 (ideally on the Pi).

Examples:
  pwsh ./build-electron.ps1                 # build for the current host OS
  pwsh ./build-electron.ps1 -Targets win    # Windows: NSIS + portable
  pwsh ./build-electron.ps1 -Targets macos  # macOS: DMG/ZIP (per electron-builder defaults/config)
  pwsh ./build-electron.ps1 -Targets pi     # Raspberry Pi OS 64-bit: .deb for arm64
#>

param(
  [string]$Python = "python",
  [string[]]$Targets = @(),
  [switch]$SkipPythonInstall,
  [switch]$SkipNodeInstall,
  [switch]$SkipBackendBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$uiPath = Join-Path $repoRoot "ui"
$electronPath = Join-Path $repoRoot "electron"

function Resolve-Targets {
  param(
    [string[]]$Requested
  )

  $normalized = @()
  foreach ($target in ($Requested | Where-Object { $_ })) {
    $value = $target.Trim().ToLowerInvariant()
    if (
      $value -eq "pi" -or
      $value -eq "pi64" -or
      $value -eq "rpi" -or
      $value -eq "rpi64" -or
      $value -eq "raspberrypi" -or
      $value -eq "raspberrypi64" -or
      $value -eq "raspberry-pi" -or
      $value -eq "raspberry-pi64"
    ) {
      $value = "linux-arm64"
    }
    if ($value -eq "linux") {
      $value = "linux-arm64"
    }
    if ($value -eq "macos" -or $value -eq "osx") {
      $value = "mac"
    }
    if ($value -eq "win") {
      $value = "windows"
    }
    if ($value -eq "all") {
      $normalized = @("windows", "mac", "linux-arm64")
      break
    }
    $normalized += $value
  }

  if ($normalized.Count -eq 0) {
    if ($env:OS -eq "Windows_NT") {
      return @("windows")
    }
    if ($IsMacOS) {
      return @("mac")
    }
    if ($IsLinux) {
      return @("linux-arm64")
    }
    return @("windows")
  }

  $supported = @("windows", "mac", "linux-arm64")
  $unsupported = $normalized | Where-Object { $supported -notcontains $_ }
  if ($unsupported.Count -gt 0) {
    throw "Unsupported target(s): $($unsupported -join ', '). Supported: windows, mac, linux-arm64, all."
  }
  return $normalized | Select-Object -Unique
}

function Get-HostArchitecture {
  try {
    return [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
  } catch {
    if ($env:PROCESSOR_ARCHITECTURE) {
      return $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()
    }
    return ""
  }
}

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )

  $command = Get-Command $FilePath -ErrorAction SilentlyContinue
  $resolved = if ($command) { $command.Source } else { $FilePath }
  & $resolved @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$FilePath failed with exit code $LASTEXITCODE."
  }
}

function Install-NpmDependencies {
  param(
    [string]$Path
  )

  if (-not (Test-Path (Join-Path $Path "package.json"))) {
    throw "Missing package.json in $Path"
  }

  Push-Location $Path
  try {
    if (Test-Path (Join-Path $Path "package-lock.json")) {
      try {
        Invoke-Checked "npm" @("ci")
        return
      } catch {
        Invoke-Checked "npm" @("install")
        return
      }
    }
    Invoke-Checked "npm" @("install")
  } finally {
    Pop-Location
  }
}

function Assert-TargetSupportedOnHost {
  param(
    [string]$Target
  )

  $isWindows = $env:OS -eq "Windows_NT"
  $arch = Get-HostArchitecture

  if ($Target -eq "windows" -and -not $isWindows) {
    throw "windows builds must be created on Windows."
  }
  if ($Target -eq "mac" -and -not $IsMacOS) {
    throw "mac builds must be created on macOS (run this script with pwsh on a Mac)."
  }
  if ($Target -eq "linux-arm64" -and -not $IsLinux) {
    throw "linux-arm64 (Raspberry Pi OS 64-bit) builds must be created on Linux."
  }
  if ($Target -eq "linux-arm64" -and $arch -ne "" -and $arch -ne "arm64") {
    throw "linux-arm64 builds require an arm64 Linux host (detected: $arch)."
  }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required but was not found on PATH."
}

$resolvedTargets = Resolve-Targets $Targets
foreach ($target in $resolvedTargets) {
  Assert-TargetSupportedOnHost $target
}
Write-Host "Building targets: $($resolvedTargets -join ', ')"

if (-not $SkipPythonInstall) {
  Invoke-Checked $Python @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Checked $Python @("-m", "pip", "install", "-e", ".")
  Invoke-Checked $Python @("-m", "pip", "install", "pyinstaller")
}

if (-not $SkipNodeInstall) {
  Install-NpmDependencies $uiPath
  Install-NpmDependencies $electronPath
}

Push-Location $electronPath
try {
  Invoke-Checked "npm" @("run", "build:ui")
  Invoke-Checked "npm" @("run", "build:electron")
  if (-not $SkipBackendBuild) {
    Invoke-Checked "npm" @("run", "build:backend")
  }

  foreach ($target in $resolvedTargets) {
    if ($target -eq "windows") {
      Invoke-Checked "npx" @("electron-builder", "--win")
      continue
    }
    if ($target -eq "mac") {
      Invoke-Checked "npx" @("electron-builder", "--mac")
      continue
    }
    if ($target -eq "linux-arm64") {
      Invoke-Checked "npx" @("electron-builder", "--linux", "--arm64")
      continue
    }
  }
} finally {
  Pop-Location
}

Write-Host "Done. Artifacts are in electron/dist-release."
