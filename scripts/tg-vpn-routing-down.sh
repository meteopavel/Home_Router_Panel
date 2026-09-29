#!/usr/bin/env bash
# tg-vpn-routing-down.sh — убирает туннельную часть маршрутизации AWG (awg0)
#
# Вызывается как PreDown в awg0.conf.
# Удаляет только то, что относится к туннелю; другие правила iptables не затрагивает.
#
# ВАЖНО (fail-closed): ipset'ы и sentinel-правила FORWARD (DROP не-через-awg0)
# здесь НЕ удаляются и ipset'ы не очищаются — при остановленном туннеле трафик
# AWG-списков должен блокироваться, а не уходить напрямую через WAN провайдера.
# Sentinel-правила и наполнение ipset'ов перестраивает tg-vpn-routing-up.sh
# (PostUp / awg-failclosed.service); их ручное снятие — осознанное действие
# отдельными командами iptables/ipset.
#
# УСТАНОВКА:
#   sudo cp scripts/tg-vpn-routing-down.sh /usr/local/sbin/
#   sudo chmod 755 /usr/local/sbin/tg-vpn-routing-down.sh
#   sudo chown root:root /usr/local/sbin/tg-vpn-routing-down.sh

set -uo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

AWG_IFACE="awg0"
LAN_IFACE="enp2s0"
LOCAL_NET="192.168.100.0/24"
FWMARK="0x66"
FWMARK_MASK="0xff"
ROUTE_TABLE="100"
CHAIN="TG_VPN_ROUTING"

log() { echo "[awg-routing-down] $*"; }

log "Удаление ip rule fwmark $FWMARK/$FWMARK_MASK → table $ROUTE_TABLE..."
ip rule del fwmark "$FWMARK/$FWMARK_MASK" table "$ROUTE_TABLE" 2>/dev/null || true

log "Очистка ip route table $ROUTE_TABLE..."
ip route flush table "$ROUTE_TABLE" 2>/dev/null || true

log "Удаление цепочки $CHAIN из mangle..."
# Сначала удаляем jump из PREROUTING (точное повторение правила из up-скрипта)
iptables -t mangle -D PREROUTING -i "$LAN_IFACE" ! -d "$LOCAL_NET" -j "$CHAIN" 2>/dev/null || true
# Затем очищаем и удаляем саму цепочку
iptables -t mangle -F "$CHAIN" 2>/dev/null || true
iptables -t mangle -X "$CHAIN" 2>/dev/null || true

log "Удаление NAT MASQUERADE для $AWG_IFACE..."
iptables -t nat -D POSTROUTING -o "$AWG_IFACE" -j MASQUERADE 2>/dev/null || true

log "Удаление FORWARD правил..."
iptables -D FORWARD -i "$LAN_IFACE" -o "$AWG_IFACE" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i "$AWG_IFACE" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true

log "Туннельная часть удалена. ipset'ы и sentinel DROP сохранены (fail-closed)."
