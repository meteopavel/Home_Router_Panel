#!/usr/bin/env bash
# tg-vpn-routing-up.sh — применяет маршрутизацию через AWG (awg0) + fail-closed guard
#
# Читает конфигурацию из /etc/home-router-panel/awg/
# Вызывается как PostUp в awg0.conf, кнопкой «Применить маршрутизацию» в панели
# и юнитом awg-failclosed.service (guard-режим при загрузке / таймер обновления).
#
# Идемпотентен: безопасно запускать повторно без дублирования правил.
# Для iptables mangle использует отдельную цепочку TG_VPN_ROUTING —
# она сбрасывается и перестраивается при каждом запуске. Другие правила не затрагиваются.
#
# FAIL-CLOSED: резолв доменов, ipset'ы и sentinel-правила FORWARD строятся ВСЕГДА,
# независимо от наличия awg0. Sentinel: пакеты к сетям AWG-списков (и от MAC-устройств),
# выходящие НЕ через awg0 — DROP. Если туннель упал или остановлен, трафик списков
# не уходит напрямую через WAN провайдера (раньше уходил молча).
#
# УСТАНОВКА:
#   sudo cp scripts/tg-vpn-routing-up.sh /usr/local/sbin/
#   sudo chmod 755 /usr/local/sbin/tg-vpn-routing-up.sh
#   sudo chown root:root /usr/local/sbin/tg-vpn-routing-up.sh
#
# ВНИМАНИЕ: перед установкой убедитесь, что файлы конфигурации существуют:
#   /etc/home-router-panel/awg/tg_nets.txt
#   /etc/home-router-panel/awg/*_domains.txt  — любые файлы вида <name>_domains.txt подхватываются автоматически
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

# ── Сериализация: PostUp/кнопка/таймер могут пересечься ───────────────────────
mkdir -p /run
exec 200>/run/tg-vpn-routing.lock
if ! flock -n 200; then
    warn "другой экземпляр уже работает — выходим"
    exit 0
fi

# ── Режим: awg0 есть или guard без туннеля ────────────────────────────────────
if ip link show "$AWG_IFACE" &>/dev/null; then
    AWG_UP="yes"
    log "Интерфейс $AWG_IFACE найден — полная маршрутизация."
else
    AWG_UP="no"
    warn "Интерфейс $AWG_IFACE отсутствует — режим fail-closed guard: ipset'ы и sentinel DROP строятся, туннельная часть пропускается. Трафик AWG-списков блокируется до подъёма туннеля."
fi

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

# sentinel-правило в FORWARD: вставить первым, если его ещё нет
ensure_fwd_drop() {
    if ! iptables -C FORWARD "$@" -j DROP 2>/dev/null; then
        iptables -I FORWARD 1 "$@" -j DROP
    fi
}

# ── Forwarding ────────────────────────────────────────────────────────────────

log "Настройка ip_forward..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# ── Цепочка TG_VPN_ROUTING (маркировка) ───────────────────────────────────────
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

log "Sentinel DROP: tg_nets не через $AWG_IFACE..."
ensure_fwd_drop -m set --match-set tg_nets dst ! -o "$AWG_IFACE"

# ── ipset: домены (все *_domains.txt из CONF_DIR) ────────────────────────────

for domains_file in "$CONF_DIR"/*_domains.txt; do
    [ -f "$domains_file" ] || continue
    base="$(basename "$domains_file" .txt)"   # напр. figma_domains
    ipset_name="${base%_domains}_nets"         # напр. figma_nets

    log "Резолвинг доменов из $domains_file..."
    ensure_ipset "$ipset_name" "hash:ip"
    count=0
    while IFS= read -r domain; do
        while IFS= read -r ip; do
            ipset add "$ipset_name" "$ip" 2>/dev/null || true
            (( count++ )) || true
        done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u || true)
    done < <(read_conf_lines "$(basename "$domains_file")")
    log "  $ipset_name: $count IP"

    iptables -t mangle -A "$CHAIN" -m set --match-set "$ipset_name" dst -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"

    log "Sentinel DROP: $ipset_name не через $AWG_IFACE..."
    ensure_fwd_drop -m set --match-set "$ipset_name" dst ! -o "$AWG_IFACE"
done

# ── MAC-устройства ────────────────────────────────────────────────────────────
# MAC-правила добавляем в цепочку напрямую.
# -i enp2s0 уже гарантирован jump-правилом в PREROUTING.

log "Настройка MAC-правил из $CONF_DIR/vpn_device_macs.txt..."
count=0
while IFS= read -r mac; do
    iptables -t mangle -A "$CHAIN" -m mac --mac-source "$mac" -j MARK --set-xmark "$FWMARK/$FWMARK_MASK"
    log "Sentinel DROP: $mac не через $AWG_IFACE..."
    ensure_fwd_drop -m mac --mac-source "$mac" ! -o "$AWG_IFACE"
    (( count++ )) || true
done < <(read_conf_lines "vpn_device_macs.txt")
log "  MAC-правил: $count"

# ── Туннельная часть: только при живом awg0 ───────────────────────────────────

if [[ "$AWG_UP" == "yes" ]]; then
    log "Настройка ip route table $ROUTE_TABLE..."
    if ! ip route show table "$ROUTE_TABLE" | grep -q "default dev $AWG_IFACE"; then
        ip route replace default dev "$AWG_IFACE" table "$ROUTE_TABLE"
    fi

    log "Настройка ip rule fwmark $FWMARK/$FWMARK_MASK → table $ROUTE_TABLE..."
    if ! ip rule show | grep -q "fwmark $FWMARK/$FWMARK_MASK.*lookup $ROUTE_TABLE"; then
        ip rule add fwmark "$FWMARK/$FWMARK_MASK" table "$ROUTE_TABLE" priority 100
    fi

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

    # Клампинг MSS для TCP через тоннель. Клиенты LAN согласуют MSS 1460 не зная
    # про awg0; ответные сегменты ~1449+ инкапсулируются во внешний UDP ~1477,
    # который на транзитном пути Frankfurt→дом может теряться (инцидент
    # 29.09.2026: 4/5 TLS-хендшейков по ~6 c из-за ретрансмиссий). MSS 1352
    # даёт внешний пакет 1420 — проверенный проходящий размер (ping DF-1392).
    log "Настройка TCPMSS clamp (MSS 1352) для $AWG_IFACE..."
    if ! iptables -t mangle -C FORWARD -o "$AWG_IFACE" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352 2>/dev/null; then
        iptables -t mangle -A FORWARD -o "$AWG_IFACE" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352
    fi
    if ! iptables -t mangle -C FORWARD -i "$AWG_IFACE" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352 2>/dev/null; then
        iptables -t mangle -A FORWARD -i "$AWG_IFACE" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352
    fi

    # ── Статические маршруты для SS-серверов ─────────────────────────────────
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
else
    warn "Пропущено (нет $AWG_IFACE): table $ROUTE_TABLE, ip rule, MASQUERADE, FORWARD ACCEPT, SS-маршруты."
fi

log "Маршрутизация через AWG применена (fail-closed guard активен)."
