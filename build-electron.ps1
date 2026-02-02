param(
  [string]$Python = "python",
  [switch]$SkipPythonInstall,
  [switch]$SkipNodeInstall,
  [switch]$SkipBackendBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

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

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required but was not found on PATH."
}

if (-not $SkipPythonInstall) {
  Invoke-Checked $Python @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Checked $Python @("-m", "pip", "install", "-e", ".")
  Invoke-Checked $Python @("-m", "pip", "install", "pyinstaller")
}

if (-not $SkipNodeInstall) {
  $uiPath = Join-Path $repoRoot "ui"
  $uiArgs = if (Test-Path (Join-Path $uiPath "package-lock.json")) { @("ci", "--prefix", $uiPath) } else { @("install", "--prefix", $uiPath) }
  try {
    Invoke-Checked "npm" $uiArgs
  } catch {
    try {
      Invoke-Checked "npm" @("install", "--prefix", $uiPath)
    } catch {
      Push-Location $uiPath
      try {
        Invoke-Checked "npm" @("install")
      } finally {
        Pop-Location
      }
    }
  }

  $electronPath = Join-Path $repoRoot "electron"
  $electronArgs = if (Test-Path (Join-Path $electronPath "package-lock.json")) { @("ci", "--prefix", $electronPath) } else { @("install", "--prefix", $electronPath) }
  try {
    Invoke-Checked "npm" $electronArgs
  } catch {
    try {
      Invoke-Checked "npm" @("install", "--prefix", $electronPath)
    } catch {
      Push-Location $electronPath
      try {
        Invoke-Checked "npm" @("install")
      } finally {
        Pop-Location
      }
    }
  }
}

if (-not $SkipBackendBuild) {
  Push-Location (Join-Path $repoRoot "electron")
  try {
    Invoke-Checked "npm" @("run", "build:backend")
  } finally {
    Pop-Location
  }
}

Push-Location (Join-Path $repoRoot "electron")
try {
  Invoke-Checked "npm" @("run", "dist", "--", "--win")
} finally {
  Pop-Location
}

Write-Host "Done. Artifacts are in electron\\dist-release."
