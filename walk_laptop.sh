#!/usr/bin/env bash
# Walk 127.0.0.1 with all three SNMP versions and print each summary.
set -euo pipefail

HOST=127.0.0.1
OUT=$(mktemp -d)

cd "$(dirname "$0")/oidtrace"

for version in v1 v2c v3; do
    echo "=== $version ==="
    case $version in
        v3) uv run oidtrace walk v3 "$HOST" --user noAuthUser --out "$OUT" ;;
        *)  uv run oidtrace walk "$version" "$HOST" --out "$OUT" ;;
    esac
    echo
done

rm -rf "$OUT"
