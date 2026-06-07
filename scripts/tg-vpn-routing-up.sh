#!/usr/bin/env bash
# tg-vpn-routing-up.sh — применяет маршрутизацию через AWG (awg0)
#
# Читает конфигурацию из /etc/home-router-panel/awg/
# Вызывается как PostUp в awg0.conf и кнопкой «Применить маршрутизацию» в панели.
#
# УСТАНОВКА:
#   sudo cp scripts/tg-vpn-routing-up.sh /usr/local/sbin/
#   sudo chmod 755 /usr/local/sbin/tg-vpn-routing-up.sh
#   sudo chown root:root /usr/local/sbin/tg-vpn-routing-up.sh
#
# ВНИМАНИЕ: перед установкой убедитесь, что файлы конфигурации существуют:
#   /etc/home-router-panel/awg/tg_nets.txt
#   /etc/home-router-panel/awg/figma_domains.txt
#   /etc/home-router-panel/awg/claude_domains.txt
#   /etc/home-router-panel/awg/vpn_device_macs.txt

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

AWG_IFACE="awg0"
LAN_IFACE="enp2s0"
CONF_DIR="/etc/home-router-panel/awg"
FWMARK="0x66"
FWMARK_MASK="0xff"
ROUTE_TABLE="100"

log() { echo "[awg-routing] $*"; }
warn() { echo "[awg-routing] WARN: $*" >&2; }

# ── Helpers ──────────────────────────────────────────────────────────────────

read_conf_lines() {
    local file="$CONF_DIR/$1"
    if [[ ! -f "$file" ]]; then
        warn "Файл не найден: $file"
        return
    fi
    # Пропускаем пустые строки и комментарии
    grep -v -E '^\s*(#|$)' "$file" | awk '{print $1}' || true
}

ensure_ipset() {
    local name="$1" type="$2"
    if ! ipset list -n "$name" &>/dev/null; then
        ipset create "$name" "$type" hashsize 4096
        log "ipset $name создан ($type)"
    else
        ipset flush "$name"
        log "ipset $name сброшен"
    fi
}

# ── Таблица маршрутизации ─────────────────────────────────────────────────────

log "Настройка ip route table $ROUTE_TABLE..."
if ! ip route show table "$ROUTE_TABLE" | grep -q "default dev $AWG_IFACE"; then
    ip route replace default dev "$AWG_IFACE" table "$ROUTE_TABLE"
fi

log "Настройка ip rule fwmark $FWMARK/$FWMARK_MASK → table $ROUTE_TABLE..."
if ! ip rule show | grep -q "fwmark $FWMARK/$FWMARK_MASK.*lookup $ROUTE_TABLE"; then
    ip rule add fwmark "$FWMARK/$FWMARK_MASK" table "$ROUTE_TABLE" priority 100
fi

# ── NAT и forwarding ─────────────────────────────────────────────────────────

log "Настройка ip_forward..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null

log "Настройка MASQUERADE для $AWG_IFACE..."
if ! iptables -t nat -C POSTROUTING -o "$AWG_IFACE" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -o "$AWG_IFACE" -j MASQUERADE
fi

log "Настройка FORWARD правил..."
for dir in "-i $LAN_IFACE -o $AWG_IFACE" "-i $AWG_IFACE -o $LAN_IFACE -m state --state RELATED,ESTABLISHED"; do
    # shellcheck disable=SC2086
    if ! iptables -C FORWARD $dir -j ACCEPT 2>/dev/null; then
        # shellcheck disable=SC2086
        iptables -A FORWARD $dir -j ACCEPT
    fi
done

# ── ipset: Telegram сети ──────────────────────────────────────────────────────

log "Заполнение ipset tg_nets из $CONF_DIR/tg_nets.txt..."
ensure_ipset tg_nets "hash:net"
count=0
while IFS= read -r net; do
    ipset add tg_nets "$net" 2>/dev/null || true
    (( count++ )) || true
done < <(read_conf_lines "tg_nets.txt")
log "  tg_nets: $count записей"

if ! iptables -t mangle -C PREROUTING -m set --match-set tg_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK" 2>/dev/null; then
    iptables -t mangle -A PREROUTING -m set --match-set tg_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
fi

# ── ipset: Figma ──────────────────────────────────────────────────────────────

log "Резолвинг доменов figma из $CONF_DIR/figma_domains.txt..."
ensure_ipset figma_nets "hash:ip"
count=0
while IFS= read -r domain; do
    while IFS= read -r ip; do
        ipset add figma_nets "$ip" 2>/dev/null || true
        (( count++ )) || true
    done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u || true)
done < <(read_conf_lines "figma_domains.txt")
log "  figma_nets: $count IP"

if ! iptables -t mangle -C PREROUTING -m set --match-set figma_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK" 2>/dev/null; then
    iptables -t mangle -A PREROUTING -m set --match-set figma_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
fi

# ── ipset: Claude/Anthropic ───────────────────────────────────────────────────

log "Резолвинг доменов claude из $CONF_DIR/claude_domains.txt..."
ensure_ipset claude_nets "hash:ip"
count=0
while IFS= read -r domain; do
    while IFS= read -r ip; do
        ipset add claude_nets "$ip" 2>/dev/null || true
        (( count++ )) || true
    done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u || true)
done < <(read_conf_lines "claude_domains.txt")
log "  claude_nets: $count IP"

if ! iptables -t mangle -C PREROUTING -m set --match-set claude_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK" 2>/dev/null; then
    iptables -t mangle -A PREROUTING -m set --match-set claude_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
fi

# ── MAC-устройства ────────────────────────────────────────────────────────────

log "Настройка правил для MAC-устройств из $CONF_DIR/vpn_device_macs.txt..."
count=0
while IFS= read -r mac; do
    if ! iptables -t mangle -C PREROUTING -i "$LAN_IFACE" -m mac --mac-source "$mac" -j MARK --set-xmark "$FWMARK/$FWMARK_MASK" 2>/dev/null; then
        iptables -t mangle -A PREROUTING -i "$LAN_IFACE" -m mac --mac-source "$mac" -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
        (( count++ )) || true
    fi
done < <(read_conf_lines "vpn_device_macs.txt")
log "  Добавлено MAC-правил: $count"

log "Маршрутизация через AWG применена."
