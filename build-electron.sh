#!/usr/bin/env bash
#
# Build Electron desktop artifacts for RCH (macOS-friendly shell translation).
#
# Notes:
# - Windows builds must run on Windows.
# - macOS builds must run on macOS.
# - Raspberry Pi OS 64-bit builds must run on Linux arm64 (ideally on the Pi).
#
# Examples:
#   ./build-electron.sh                      # build for the current host OS
#   ./build-electron.sh --targets win        # Windows: NSIS + portable
#   ./build-electron.sh --targets macos      # macOS: DMG/ZIP (per electron-builder defaults/config)
#   ./build-electron.sh --targets pi         # Raspberry Pi OS 64-bit: .deb for arm64
#

set -euo pipefail

PYTHON="python3"
TARGETS=()
SKIP_PYTHON_INSTALL=0
SKIP_NODE_INSTALL=0
SKIP_BACKEND_BUILD=0

usage() {
  cat <<'EOF'
Usage: ./build-electron.sh [options]

Options:
  --python <path>             Python executable to use (default: python3)
  --targets <list>            Comma-separated targets: win, macos, pi, all
  --skip-python-install       Skip pip installs and pyinstaller install
  --skip-node-install         Skip npm install/ci in ui and electron
  --skip-backend-build        Skip backend build step
  -h, --help                  Show this help
EOF
}

require_arg() {
  local flag="$1"
  local value="${2:-}"
  if [ -z "$value" ]; then
    echo "Missing value for $flag" >&2
    usage
    exit 1
  fi
}

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

add_targets() {
  local raw="$1"
  local parts=()
  local IFS=','
  read -r -a parts <<< "$raw"
  local part
  for part in "${parts[@]}"; do
    if [ -n "$part" ]; then
      TARGETS+=("$part")
    fi
  done
}

is_macos() {
  [ "$(uname -s)" = "Darwin" ]
}

is_linux() {
  [ "$(uname -s)" = "Linux" ]
}

get_host_arch() {
  local arch
  arch="$(uname -m 2>/dev/null || true)"
  case "$arch" in
    arm64|aarch64)
      echo "arm64"
      ;;
    x86_64|amd64)
      echo "x86_64"
      ;;
    *)
      echo "$arch"
      ;;
  esac
}

resolve_targets() {
  local normalized=()
  local target
  for target in "$@"; do
    if [ -z "$target" ]; then
      continue
    fi
    local value
    value="$(printf "%s" "$target" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$value" in
      pi|pi64|rpi|rpi64|raspberrypi|raspberrypi64|raspberry-pi|raspberry-pi64)
        value="linux-arm64"
        ;;
      linux)
        value="linux-arm64"
        ;;
      macos|osx)
        value="mac"
        ;;
      win)
        value="windows"
        ;;
      all)
        echo "windows mac linux-arm64"
        return
        ;;
    esac
    normalized+=("$value")
  done

  if [ "${#normalized[@]}" -eq 0 ]; then
    if [ "${OS:-}" = "Windows_NT" ]; then
      normalized=("windows")
    elif is_macos; then
      normalized=("mac")
    elif is_linux; then
      normalized=("linux-arm64")
    else
      normalized=("windows")
    fi
  fi

  local supported=("windows" "mac" "linux-arm64")
  local unsupported=()
  for target in "${normalized[@]}"; do
    if ! contains "$target" "${supported[@]}"; then
      unsupported+=("$target")
    fi
  done

  if [ "${#unsupported[@]}" -gt 0 ]; then
    echo "Unsupported target(s): ${unsupported[*]}. Supported: windows, mac, linux-arm64, all." >&2
    exit 1
  fi

  local unique=()
  for target in "${normalized[@]}"; do
    if ! contains "$target" "${unique[@]-}"; then
      unique+=("$target")
    fi
  done

  printf "%s " "${unique[@]}"
  printf "\n"
}

assert_target_supported_on_host() {
  local target="$1"
  local arch
  arch="$(get_host_arch)"

  if [ "$target" = "windows" ] && [ "${OS:-}" != "Windows_NT" ]; then
    echo "windows builds must be created on Windows." >&2
    exit 1
  fi
  if [ "$target" = "mac" ] && ! is_macos; then
    echo "mac builds must be created on macOS (run this script on a Mac)." >&2
    exit 1
  fi
  if [ "$target" = "linux-arm64" ] && ! is_linux; then
    echo "linux-arm64 (Raspberry Pi OS 64-bit) builds must be created on Linux." >&2
    exit 1
  fi
  if [ "$target" = "linux-arm64" ] && [ -n "$arch" ] && [ "$arch" != "arm64" ]; then
    echo "linux-arm64 builds require an arm64 Linux host (detected: $arch)." >&2
    exit 1
  fi
}

install_npm_dependencies() {
  local path="$1"
  if [ ! -f "$path/package.json" ]; then
    echo "Missing package.json in $path" >&2
    exit 1
  fi

  pushd "$path" >/dev/null
  if [ -f "$path/package-lock.json" ]; then
    if ! npm ci; then
      npm install
    fi
  else
    npm install
  fi
  popd >/dev/null
}

while [ $# -gt 0 ]; do
  case "$1" in
    --python)
      require_arg "$1" "${2:-}"
      PYTHON="$2"
      shift 2
      ;;
    --targets|-t)
      require_arg "$1" "${2:-}"
      add_targets "$2"
      shift 2
      ;;
    --skip-python-install)
      SKIP_PYTHON_INSTALL=1
      shift
      ;;
    --skip-node-install)
      SKIP_NODE_INSTALL=1
      shift
      ;;
    --skip-backend-build)
      SKIP_BACKEND_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but was not found on PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_PATH="$SCRIPT_DIR/ui"
ELECTRON_PATH="$SCRIPT_DIR/electron"

RESOLVED_TARGETS=()
if [ "${#TARGETS[@]}" -gt 0 ]; then
  read -r -a RESOLVED_TARGETS <<< "$(resolve_targets "${TARGETS[@]}")"
else
  read -r -a RESOLVED_TARGETS <<< "$(resolve_targets)"
fi

for target in "${RESOLVED_TARGETS[@]-}"; do
  assert_target_supported_on_host "$target"
done

echo "Building targets: ${RESOLVED_TARGETS[*]-}"

if [ "$SKIP_PYTHON_INSTALL" -eq 0 ]; then
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -e .
  "$PYTHON" -m pip install pyinstaller
fi

if [ "$SKIP_NODE_INSTALL" -eq 0 ]; then
  install_npm_dependencies "$UI_PATH"
  install_npm_dependencies "$ELECTRON_PATH"
fi

pushd "$ELECTRON_PATH" >/dev/null
  npm run sync:version
  npm run build:ui
  npm run build:electron
  if [ "$SKIP_BACKEND_BUILD" -eq 0 ]; then
    npm run build:backend
  fi

  for target in "${RESOLVED_TARGETS[@]-}"; do
    if [ "$target" = "windows" ]; then
      npx electron-builder --win
      continue
    fi
    if [ "$target" = "mac" ]; then
      npx electron-builder --mac
      continue
    fi
    if [ "$target" = "linux-arm64" ]; then
      npx electron-builder --linux --arm64
      continue
    fi
  done
popd >/dev/null

echo "Done. Artifacts are in electron/dist-release."
