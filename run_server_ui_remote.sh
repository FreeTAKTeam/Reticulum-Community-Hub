#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

resolve_public_host() {
  local detected_ip=""
  local detected_name=""

  if command -v hostname >/dev/null 2>&1; then
    detected_ip="$(hostname -I 2>/dev/null | awk 'NF { print $1; exit }')"
    if [[ -n "$detected_ip" ]]; then
      printf '%s\n' "$detected_ip"
      return
    fi

    detected_name="$(hostname 2>/dev/null || true)"
    if [[ -n "$detected_name" && "$detected_name" != "(none)" ]]; then
      printf '%s\n' "$detected_name"
      return
    fi
  fi

  printf '127.0.0.1\n'
}

ensure_npm() {
  local current_uid
  local -a elevate=()

  if command -v npm >/dev/null 2>&1; then
    return
  fi

  echo "npm was not found in PATH. Attempting to install Node.js and npm..."

  current_uid="${EUID:-$(id -u)}"
  if [[ "$current_uid" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      elevate=(sudo)
    else
      echo "npm is missing and this script needs root privileges to install it." >&2
      echo "Install Node.js/npm manually or rerun this script with sudo." >&2
      exit 1
    fi
  fi

  if command -v apt-get >/dev/null 2>&1; then
    "${elevate[@]}" apt-get update
    "${elevate[@]}" apt-get install -y nodejs npm
  elif command -v dnf >/dev/null 2>&1; then
    "${elevate[@]}" dnf install -y nodejs npm
  elif command -v yum >/dev/null 2>&1; then
    "${elevate[@]}" yum install -y nodejs npm
  elif command -v apk >/dev/null 2>&1; then
    "${elevate[@]}" apk add --no-cache nodejs npm
  elif command -v pacman >/dev/null 2>&1; then
    "${elevate[@]}" pacman -Sy --noconfirm nodejs npm
  elif command -v zypper >/dev/null 2>&1; then
    "${elevate[@]}" zypper --non-interactive install nodejs npm
  else
    echo "Could not auto-install npm: no supported package manager was found." >&2
    echo "Install Node.js 20 LTS and npm manually, then rerun this script." >&2
    exit 1
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is still unavailable after the install attempt." >&2
    exit 1
  fi
}

VENV_DIR="${VENV_DIR:-.venv}"
RTH_STORAGE_DIR="${RTH_STORAGE_DIR:-RTH_Store}"
RTH_HUB_MODE="${RTH_HUB_MODE:-embedded}"
RTH_DAEMON="${RTH_DAEMON:-0}"
RTH_SERVICES="${RTH_SERVICES:-}"
RTH_LOG_LEVEL="${RTH_LOG_LEVEL:-}"
RTH_API_HOST="${RTH_API_HOST:-0.0.0.0}"
RTH_API_PORT="${RTH_API_PORT:-8000}"
RTH_UI_HOST="${RTH_UI_HOST:-0.0.0.0}"
RTH_UI_PORT="${RTH_UI_PORT:-5173}"
RTH_PUBLIC_HOST="${RTH_PUBLIC_HOST:-$(resolve_public_host)}"
RTH_PUBLIC_SCHEME="${RTH_PUBLIC_SCHEME:-http}"

if [[ -z "${RTH_API_KEY:-${RCH_API_KEY:-}}" ]]; then
  echo "Set RTH_API_KEY (or RCH_API_KEY) before starting remote access." >&2
  exit 1
fi

case "$RTH_PUBLIC_SCHEME" in
  http)
    RTH_PUBLIC_WS_SCHEME="ws"
    ;;
  https)
    RTH_PUBLIC_WS_SCHEME="wss"
    ;;
  *)
    echo "RTH_PUBLIC_SCHEME must be 'http' or 'https'." >&2
    exit 1
    ;;
esac

VITE_RTH_BASE_URL="${VITE_RTH_BASE_URL:-${RTH_PUBLIC_SCHEME}://${RTH_PUBLIC_HOST}:${RTH_API_PORT}}"
EFFECTIVE_WS_BASE_URL="${VITE_RTH_WS_BASE_URL:-${RTH_PUBLIC_WS_SCHEME}://${RTH_PUBLIC_HOST}:${RTH_API_PORT}}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python 3.10+ is required but was not found in PATH." >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment in '${VENV_DIR}'..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

VENV_PATH="$VENV_DIR"
if [[ "$VENV_PATH" != /* ]]; then
  VENV_PATH="${SCRIPT_DIR}/${VENV_PATH}"
fi
PYTHON_EXE="${VENV_PATH}/bin/python"

STORAGE_DIR_PATH="$RTH_STORAGE_DIR"
if [[ "$STORAGE_DIR_PATH" != /* ]]; then
  STORAGE_DIR_PATH="${SCRIPT_DIR}/${STORAGE_DIR_PATH}"
fi

echo "Installing backend from local source..."
"$PYTHON_EXE" -m pip install --upgrade pip
"$PYTHON_EXE" -m pip install -e .

echo "Ensuring WebSocket support for Uvicorn..."
if ! "$PYTHON_EXE" -c "import websockets" >/dev/null 2>&1; then
  "$PYTHON_EXE" -m pip install "websockets>=12,<14"
fi

ensure_npm

if [[ ! -d "ui/node_modules" ]]; then
  echo "Installing UI dependencies..."
  (cd ui && npm install)
fi

mkdir -p "$STORAGE_DIR_PATH"

HUB_FLAGS=()
if [[ "$RTH_HUB_MODE" == "embedded" ]]; then
  HUB_FLAGS+=("--embedded")
fi
if [[ "$RTH_DAEMON" == "1" ]]; then
  HUB_FLAGS+=("--daemon")
fi
if [[ -n "${RTH_DISPLAY_NAME:-}" ]]; then
  HUB_FLAGS+=("--display_name" "$RTH_DISPLAY_NAME")
fi
if [[ -n "$RTH_LOG_LEVEL" ]]; then
  HUB_FLAGS+=("--log-level" "$RTH_LOG_LEVEL")
fi

IFS=',' read -r -a SERVICES_ARR <<< "$RTH_SERVICES"
for service in "${SERVICES_ARR[@]}"; do
  service_trimmed="$(echo "$service" | xargs)"
  if [[ -n "$service_trimmed" ]]; then
    HUB_FLAGS+=("--service" "$service_trimmed")
  fi
done

echo "Starting hub + northbound API at ${VITE_RTH_BASE_URL} (bind ${RTH_API_HOST}:${RTH_API_PORT})"
(cd "$VENV_PATH" && "$PYTHON_EXE" -m reticulum_telemetry_hub.northbound.gateway \
  --storage_dir "$STORAGE_DIR_PATH" \
  --api-host "$RTH_API_HOST" \
  --api-port "$RTH_API_PORT" \
  "${HUB_FLAGS[@]}") &
BACKEND_PID=$!

echo "Starting UI dev server at http://${RTH_PUBLIC_HOST}:${RTH_UI_PORT} (bind ${RTH_UI_HOST}:${RTH_UI_PORT})"
if [[ -n "${VITE_RTH_WS_BASE_URL:-}" ]]; then
  (
    cd ui && \
      VITE_RTH_BASE_URL="$VITE_RTH_BASE_URL" \
      VITE_RTH_WS_BASE_URL="$VITE_RTH_WS_BASE_URL" \
      npm run dev -- --host "$RTH_UI_HOST" --port "$RTH_UI_PORT"
  ) &
else
  (
    cd ui && \
      VITE_RTH_BASE_URL="$VITE_RTH_BASE_URL" \
      npm run dev -- --host "$RTH_UI_HOST" --port "$RTH_UI_PORT"
  ) &
fi
UI_PID=$!

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  kill "$BACKEND_PID" "$UI_PID" >/dev/null 2>&1 || true
  wait "$BACKEND_PID" "$UI_PID" >/dev/null 2>&1 || true
  exit "$code"
}

trap cleanup EXIT INT TERM

echo
echo "Hub+API: storage=${RTH_STORAGE_DIR}  mode=${RTH_HUB_MODE}  daemon=${RTH_DAEMON}  services=${RTH_SERVICES}"
echo "API URL: ${VITE_RTH_BASE_URL}"
if [[ -n "${VITE_RTH_WS_BASE_URL:-}" ]]; then
  echo "WS URL:  ${VITE_RTH_WS_BASE_URL} (explicit override)"
else
  echo "WS URL:  ${EFFECTIVE_WS_BASE_URL} (derived from API URL in the UI)"
fi
echo "UI URL:  http://${RTH_PUBLIC_HOST}:${RTH_UI_PORT}"
echo
echo "Press Ctrl+C to stop both processes."

wait -n "$BACKEND_PID" "$UI_PID"
