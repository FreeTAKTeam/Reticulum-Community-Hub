#!/usr/bin/env bash
# Installs project dependencies in a local venv (if needed) and launches the hub.
set -euo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
else
    echo "Python 3.10+ is required but was not found in PATH." >&2
    exit 1
fi

VENV_DIR="${VENV_DIR:-.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e .

exec python -m reticulum_telemetry_hub.reticulum_server "$@"
