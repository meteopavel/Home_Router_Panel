#!/usr/bin/env bash
# tg-vpn-routing-up.sh — применяет маршрутизацию через AWG (awg0)
#
# Читает конфигурацию из /etc/home-router-panel/awg/
# Вызывается как PostUp в awg0.conf и кнопкой «Применить маршрутизацию» в панели.
#
# Идемпотентен: безопасно запускать повторно без дублирования правил.
# Для iptables mangle использует отдельную цепочку TG_VPN_ROUTING —
# она сбрасывается и перестраивается при каждом запуске. Другие правила не затрагиваются.
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
#   /etc/home-router-panel/awg/bebra_domains.txt
#   /etc/home-router-panel/awg/ss_server_ips.txt   — IP SS-серверов (маршрутизируются через awg0 напрямую)
#   /etc/home-router-panel/awg/vpn_device_macs.txt

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

AWG_IFACE="awg0"
LAN_IFACE="enp2s0"
LOCAL_NET="192.168.100.0/24"
CONF_DIR="/etc/home-router-panel/awg"
FWMARK="0x66"
FWMARK_MASK="0xff"
ROUTE_TABLE="100"
CHAIN="TG_VPN_ROUTING"

log() { echo "[awg-routing] $*"; }
warn() { echo "[awg-routing] WARN: $*" >&2; }

# ── Helpers ───────────────────────────────────────────────────────────────────

read_conf_lines() {
    local file="$CONF_DIR/$1"
    if [[ ! -f "$file" ]]; then
        warn "Файл не найден: $file"
        return
    fi
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

# ── NAT и forwarding ──────────────────────────────────────────────────────────

log "Настройка ip_forward..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null

log "Настройка MASQUERADE для $AWG_IFACE..."
if ! iptables -t nat -C POSTROUTING -o "$AWG_IFACE" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -o "$AWG_IFACE" -j MASQUERADE
fi

log "Настройка FORWARD правил..."
if ! iptables -C FORWARD -i "$LAN_IFACE" -o "$AWG_IFACE" -j ACCEPT 2>/dev/null; then
    iptables -A FORWARD -i "$LAN_IFACE" -o "$AWG_IFACE" -j ACCEPT
fi
if ! iptables -C FORWARD -i "$AWG_IFACE" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -A FORWARD -i "$AWG_IFACE" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT
fi

# ── Цепочка TG_VPN_ROUTING ───────────────────────────────────────────────────
#
# Цепочка пересоздаётся при каждом запуске — правила обновляются без дублирования.
# Прыжок из PREROUTING фильтрует:
#   -i enp2s0         — только входящий LAN-трафик
#   ! -d LOCAL_NET    — исключить трафик до локальной сети

log "Пересборка цепочки $CHAIN..."
iptables -t mangle -N "$CHAIN" 2>/dev/null || true
iptables -t mangle -F "$CHAIN"

# Прыжок из PREROUTING в цепочку (добавляем один раз)
if ! iptables -t mangle -C PREROUTING -i "$LAN_IFACE" ! -d "$LOCAL_NET" -j "$CHAIN" 2>/dev/null; then
    iptables -t mangle -A PREROUTING -i "$LAN_IFACE" ! -d "$LOCAL_NET" -j "$CHAIN"
    log "  jump из PREROUTING добавлен"
fi

# ── ipset: Telegram сети ──────────────────────────────────────────────────────

log "Заполнение ipset tg_nets из $CONF_DIR/tg_nets.txt..."
ensure_ipset tg_nets "hash:net"
count=0
while IFS= read -r net; do
    ipset add tg_nets "$net" 2>/dev/null || true
    (( count++ )) || true
done < <(read_conf_lines "tg_nets.txt")
log "  tg_nets: $count записей"

iptables -t mangle -A "$CHAIN" -m set --match-set tg_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"

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

iptables -t mangle -A "$CHAIN" -m set --match-set figma_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"

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

iptables -t mangle -A "$CHAIN" -m set --match-set claude_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"

# ── ipset: Bebra ──────────────────────────────────────────────────────────────

log "Резолвинг доменов bebra из $CONF_DIR/bebra_domains.txt..."
ensure_ipset bebra_nets "hash:ip"
count=0
while IFS= read -r domain; do
    while IFS= read -r ip; do
        ipset add bebra_nets "$ip" 2>/dev/null || true
        (( count++ )) || true
    done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u || true)
done < <(read_conf_lines "bebra_domains.txt")
log "  bebra_nets: $count IP"

iptables -t mangle -A "$CHAIN" -m set --match-set bebra_nets dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"

# ── Статические маршруты для SS-серверов ─────────────────────────────────────
# IP SS-серверов заблокированы в РФ — маршрутизируем их через awg0 напрямую
# (трафик ss-local идёт через OUTPUT, не через PREROUTING, поэтому ipset не поможет).

log "Статические маршруты для SS-серверов из $CONF_DIR/ss_server_ips.txt..."
count=0
while IFS= read -r ip; do
    if ip route get "$ip" 2>/dev/null | grep -q "dev $AWG_IFACE"; then
        true  # маршрут уже есть
    else
        ip route replace "$ip" dev "$AWG_IFACE"
        (( count++ )) || true
    fi
done < <(read_conf_lines "ss_server_ips.txt")
log "  SS-маршрутов добавлено: $count"

# ── MAC-устройства ────────────────────────────────────────────────────────────
# MAC-правила добавляем в цепочку напрямую.
# -i enp2s0 уже гарантирован jump-правилом в PREROUTING.

log "Настройка MAC-правил из $CONF_DIR/vpn_device_macs.txt..."
count=0
while IFS= read -r mac; do
    iptables -t mangle -A "$CHAIN" -m mac --mac-source "$mac" -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
    (( count++ )) || true
done < <(read_conf_lines "vpn_device_macs.txt")
log "  MAC-правил: $count"

log "Маршрутизация через AWG применена."
