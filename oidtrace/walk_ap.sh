#!/usr/bin/env bash
# Walk the EAP650 access point at 192.168.1.143 via SNMPv3 authNoPriv (MD5).
set -euo pipefail

cd "$(dirname "$0")"

snmpwalk -v3 -u checkmk -l authNoPriv -a MD5 -A synology 192.168.1.143 "$@"
