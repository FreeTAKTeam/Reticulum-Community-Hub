#!/usr/bin/env bash
# Start the RTH hub + northbound API + UI dev server on Linux/Raspberry Pi.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# Override defaults via env vars:
#   VENV_DIR          (default: .venv)
#   RTH_STORAGE_DIR   (default: RTH_Store)
#   RTH_DISPLAY_NAME  (optional; when set, overrides [hub].display_name)
#   RTH_HUB_MODE      (default: embedded) [embedded|external]
#   RTH_DAEMON        (default: 0)        [1 to enable daemon mode]
#   RTH_SERVICES      (default: empty)    comma-separated (e.g. tak_cot,gpsd)
#   RTH_API_HOST      (default: 127.0.0.1)
#   RTH_API_PORT      (default: 8000)
#   VITE_RTH_BASE_URL (default: http://$RTH_API_HOST:$RTH_API_PORT)

VENV_DIR="${VENV_DIR:-.venv}"
RTH_STORAGE_DIR="${RTH_STORAGE_DIR:-RTH_Store}"
RTH_HUB_MODE="${RTH_HUB_MODE:-embedded}"
RTH_DAEMON="${RTH_DAEMON:-0}"
RTH_SERVICES="${RTH_SERVICES:-}"
RTH_API_HOST="${RTH_API_HOST:-127.0.0.1}"
RTH_API_PORT="${RTH_API_PORT:-8000}"
VITE_RTH_BASE_URL="${VITE_RTH_BASE_URL:-http://${RTH_API_HOST}:${RTH_API_PORT}}"

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

PYTHON_EXE="${VENV_DIR}/bin/python"

echo "Installing backend dependencies..."
"$PYTHON_EXE" -m pip install --upgrade pip
"$PYTHON_EXE" -m pip install -e .
echo "Ensuring WebSocket support for Uvicorn..."
if ! "$PYTHON_EXE" -c "import websockets" >/dev/null 2>&1; then
  "$PYTHON_EXE" -m pip install "websockets>=12,<14"
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required (Node.js 20 LTS recommended) but was not found in PATH." >&2
  exit 1
fi

if [[ ! -d "ui/node_modules" ]]; then
  echo "Installing UI dependencies..."
  (cd ui && npm install)
fi

mkdir -p "$RTH_STORAGE_DIR"

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

IFS=',' read -r -a SERVICES_ARR <<< "$RTH_SERVICES"
for service in "${SERVICES_ARR[@]}"; do
  service_trimmed="$(echo "$service" | xargs)"
  if [[ -n "$service_trimmed" ]]; then
    HUB_FLAGS+=("--service" "$service_trimmed")
  fi
done

echo "Starting hub + northbound API at http://${RTH_API_HOST}:${RTH_API_PORT}"
"$PYTHON_EXE" -m reticulum_telemetry_hub.northbound.gateway \
  --storage_dir "$RTH_STORAGE_DIR" \
  --api-host "$RTH_API_HOST" \
  --api-port "$RTH_API_PORT" \
  "${HUB_FLAGS[@]}" &
BACKEND_PID=$!

echo "Starting UI dev server at http://localhost:5173"
(cd ui && VITE_RTH_BASE_URL="$VITE_RTH_BASE_URL" npm run dev) &
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
echo "API: ${VITE_RTH_BASE_URL}"
echo "UI:  http://localhost:5173"
echo
echo "Press Ctrl+C to stop both processes."

wait -n "$BACKEND_PID" "$UI_PID"
