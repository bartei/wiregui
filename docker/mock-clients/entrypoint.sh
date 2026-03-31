#!/bin/sh
# WireGuard mock client — configures interface and generates traffic
set -e

echo "[*] Configuring WireGuard interface..."
ip link add wg0 type wireguard
wg setconf wg0 /etc/wireguard/wg0.conf
ip address add "${CLIENT_IP}/32" dev wg0
ip link set wg0 up

# Route traffic to the VPN subnet through the tunnel
ip route add 10.3.2.0/24 dev wg0

echo "[*] WireGuard client up: ${CLIENT_IP}"
echo "[*] Generating traffic to peers every ${PING_INTERVAL:-5}s..."

while true; do
    # Ping the server (first host in the subnet)
    ping -c 1 -W 1 10.3.2.1 > /dev/null 2>&1 || true

    # Ping other peers if specified
    for peer_ip in $PEER_IPS; do
        ping -c 1 -W 1 "$peer_ip" > /dev/null 2>&1 || true
    done

    sleep "${PING_INTERVAL:-5}"
done
