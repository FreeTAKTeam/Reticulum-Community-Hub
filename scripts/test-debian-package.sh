#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 && -f "$1" ]] || { echo "Usage: $0 <rch-server.deb>" >&2; exit 2; }
archive=$(realpath "$1")
repo=$(cd "$(dirname "$0")/.." && pwd)
docker run --rm \
  --mount "type=bind,source=$repo,target=/repo,readonly" \
  --mount "type=bind,source=$archive,target=/input/rch-server.deb,readonly" \
  --env DEBIAN_FRONTEND=noninteractive debian:12-slim \
  bash -c 'apt-get update && apt-get install -y --no-install-recommends bash adduser ca-certificates && bash /repo/packaging/debian/test-package.sh /input/rch-server.deb'
