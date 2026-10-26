#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then
  echo "Usage: $0 <patched-lxmf-checkout> <build-output-dir>" >&2
  exit 2
fi
repo=$(cd "$(dirname "$0")/.." && pwd)
lxmf=$(realpath "$1")
mkdir -p "$2"
output=$(realpath "$2")
docker build -t rch-debian-builder -f "$repo/packaging/debian/build.Dockerfile" "$repo/packaging/debian"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$repo:/work/rch:ro" -v "$lxmf:/work/LXMF-rs:ro" -v "$output:/build" \
  -e CARGO_HOME=/build/cargo -e CARGO_BUILD_JOBS=2 -e CARGO_INCREMENTAL=0 \
  -e CARGO_PROFILE_RELEASE_DEBUG=0 rch-debian-builder bash -euc '
    cd /work/rch
    CARGO_TARGET_DIR=/build/rch cargo build --locked --release -p r3akt-rch-server -p r3akt-tak-connector --bin r3akt-rch-server --bin r3akt-tak-service
    cd /work/LXMF-rs
    CARGO_TARGET_DIR=/build/lxmf cargo build --locked --release -p reticulumd --features zmq-pipeline-rpc
    mkdir -p /build/bin
    cp /build/rch/release/r3akt-rch-server /build/rch/release/r3akt-tak-service /build/lxmf/release/reticulumd /build/bin/
  '
