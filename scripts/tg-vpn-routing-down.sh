#!/usr/bin/env bash
# tg-vpn-routing-down.sh — убирает маршрутизацию через AWG (awg0)
#
# Вызывается как PreDown в awg0.conf.
#
# УСТАНОВКА:
#   sudo cp scripts/tg-vpn-routing-down.sh /usr/local/sbin/
#   sudo chmod 755 /usr/local/sbin/tg-vpn-routing-down.sh
#   sudo chown root:root /usr/local/sbin/tg-vpn-routing-down.sh

set -uo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

AWG_IFACE="awg0"
LAN_IFACE="enp2s0"
FWMARK="0x66"
FWMARK_MASK="0xff"
ROUTE_TABLE="100"

log() { echo "[awg-routing-down] $*"; }

log "Удаление ip rule fwmark $FWMARK/$FWMARK_MASK..."
ip rule del fwmark "$FWMARK/$FWMARK_MASK" table "$ROUTE_TABLE" 2>/dev/null || true

log "Удаление ip route table $ROUTE_TABLE..."
ip route flush table "$ROUTE_TABLE" 2>/dev/null || true

log "Удаление iptables mangle правил..."
iptables -t mangle -F PREROUTING 2>/dev/null || true

log "Удаление NAT MASQUERADE для $AWG_IFACE..."
iptables -t nat -D POSTROUTING -o "$AWG_IFACE" -j MASQUERADE 2>/dev/null || true

log "Удаление FORWARD правил..."
iptables -D FORWARD -i "$LAN_IFACE" -o "$AWG_IFACE" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i "$AWG_IFACE" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true

log "Удаление ipset..."
for name in tg_nets figma_nets claude_nets; do
    ipset flush "$name" 2>/dev/null || true
    ipset destroy "$name" 2>/dev/null || true
done

log "Маршрутизация через AWG удалена."
