#!/usr/bin/env bash
# Start two SNMP emulator containers, each bound to a different loopback IP.
set -euo pipefail

IMAGE=snmp-emulator
IP1=127.0.0.2
IP2=127.0.0.3
PORT=161

echo "==> Building image..."
sudo podman build -t "$IMAGE" -f Containerfile .

echo ""
echo "==> Configuring loopback aliases..."
for ip in "$IP1" "$IP2"; do
    if ip addr show lo | grep -q "${ip}/"; then
        echo "    = $ip already present"
    else
        sudo ip addr add "${ip}/8" dev lo
        echo "    + $ip added"
    fi
done

echo ""
echo ""
echo "==> Tearing down existing pods (if any)..."
sudo podman play kube pods.yaml --down 2>/dev/null || true

echo ""
echo "==> Starting pods..."
sudo podman play kube pods.yaml

echo ""
echo "Test:"
echo "  snmpget -v2c -c public ${IP1} sysDescr.0                 # fast"
echo "  snmpget -v2c -c public ${IP2} sysDescr.0                 # fast"
echo "  snmpget -v2c -c public ${IP1} 1.3.6.1.2.1.2.2.1.2.1     # slow (~3s)"
echo ""
echo "Logs:"
echo "  sudo podman logs -f snmp-device-1-emulator"
echo "  sudo podman logs -f snmp-device-2-emulator"
echo ""
echo "Stop:"
echo "  sudo podman play kube pods.yaml --down"
