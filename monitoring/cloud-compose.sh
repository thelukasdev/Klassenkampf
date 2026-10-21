#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f compose.override.yaml ]; then
    exec docker compose -f compose.yaml -f compose.override.yaml -f compose.cloud-monitoring.yaml "$@"
fi
exec docker compose -f compose.yaml -f compose.cloud-monitoring.yaml "$@"
