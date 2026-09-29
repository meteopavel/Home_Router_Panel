#!/usr/bin/env bash
# tg-vpn-routing-up.sh — применяет маршрутизацию через AWG-тоннели + fail-closed guard
#
# Мульти-туннель (feat.18):
#   awg0 «Франкфурт» — туннель по умолчанию: tg_nets, все *_domains.txt кроме
#                     перечисленных в SG_LISTS, MAC-устройства. fwmark 0x66, table 100.
#   awg1 «Сингапур»  — списки из SG_LISTS (базовые имена без «_domains»).
#                     fwmark 0x67, table 101.
# Каждый туннель независим: свой sentinel DROP («список не через свой туннель»),
# падение одного не открывает и не роняет второй.
#
# Читает конфигурацию из /etc/home-router-panel/awg/
# Вызывается как PostUp в awg0.conf и awg1.conf, кнопкой «Применить маршрутизацию»
# в панели и юнитом awg-failclosed.service (guard-режим при загрузке / таймер).
#
# Идемпотентен: безопасно запускать повторно без дублирования правил.
# Для iptables mangle использует отдельную цепочку TG_VPN_ROUTING —
# она сбрасывается и перестраивается при каждом запуске. Другие правила не затрагиваются.
#
# FAIL-CLOSED: резолв доменов, ipset'ы и sentinel-правила FORWARD строятся ВСЕГДА,
# независимо от наличия туннелей. Sentinel: пакеты к сетям AWG-списков (и от
# MAC-устройств), выходящие НЕ через свой туннель — DROP.
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

AWG_IFACE="awg0"           # Франкфурт (туннель по умолчанию)
SG_IFACE="awg1"            # Сингапур
LAN_IFACE="enp2s0"
LOCAL_NET="192.168.100.0/24"
CONF_DIR="/etc/home-router-panel/awg"
FWMARK="0x66"
FWMARK_MASK="0xff"
ROUTE_TABLE="100"
FWMARK_SG="0x67"
ROUTE_TABLE_SG="101"
CHAIN="TG_VPN_ROUTING"
# Базовые имена списков (без «_domains»), которые ходят через awg1 (Сингапур):
SG_LISTS="claude"

log() { echo "[awg-routing] $*"; }
warn() { echo "[awg-routing] WARN: $*" >&2; }

# ── Сериализация: PostUp/кнопка/таймер могут пересечься ───────────────────────
mkdir -p /run
exec 200>/run/tg-vpn-routing.lock
if ! flock -n 200; then
    warn "другой экземпляр уже работает — выходим"
    exit 0
fi

# ── Режимы: каждый туннель проверяется отдельно ───────────────────────────────
if ip link show "$AWG_IFACE" &>/dev/null; then
    AWG_UP="yes"
    log "Интерфейс $AWG_IFACE найден — полная маршрутизация (Франкфурт)."
else
    AWG_UP="no"
    warn "Интерфейс $AWG_IFACE отсутствует — его туннельная часть пропускается, sentinel DROP строится (fail-closed)."
fi
if ip link show "$SG_IFACE" &>/dev/null; then
    SG_UP="yes"
    log "Интерфейс $SG_IFACE найден — полная маршрутизация (Сингапур)."
else
    SG_UP="no"
    warn "Интерфейс $SG_IFACE отсутствует — его туннельная часть пропускается, sentinel DROP строится (fail-closed)."
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

# список ходит через awg1 (Сингапур)?
is_sg_list() {
    local base="$1"
    [[ ",$SG_LISTS," == *",$base,"* ]]
}

# устаревший sentinel вида «<ipset> не через $1» — удалить все копии.
# Нужно при переносе списка на другой туннель (feat.18: claude с awg0 на awg1),
# иначе старый DROP «не через awg0» продолжал бы душить трафик списка через awg1.
drop_stale_sentinel() {
    local ipset_name="$1" iface="$2"
    while iptables -C FORWARD -m set --match-set "$ipset_name" dst ! -o "$iface" -j DROP 2>/dev/null; do
        iptables -D FORWARD -m set --match-set "$ipset_name" dst ! -o "$iface" -j DROP
        log "  удалён устаревший sentinel: $ipset_name не через $iface"
    done
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

    if is_sg_list "${base%_domains}"; then
        mark="$FWMARK_SG"; table_iface="$SG_IFACE"
    else
        mark="$FWMARK"; table_iface="$AWG_IFACE"
    fi

    log "Резолвинг доменов из $domains_file (через $table_iface)..."
    ensure_ipset "$ipset_name" "hash:ip"
    count=0
    while IFS= read -r domain; do
        while IFS= read -r ip; do
            ipset add "$ipset_name" "$ip" 2>/dev/null || true
            (( count++ )) || true
        done < <(getent ahostsv4 "$domain" 2>/dev/null | awk '{print $1}' | sort -u || true)
    done < <(read_conf_lines "$(basename "$domains_file")")
    log "  $ipset_name: $count IP"

    iptables -t mangle -A "$CHAIN" -m set --match-set "$ipset_name" dst -j MARK --set-xmark "$mark/$FWMARK_MASK"

    # список перенесён на awg1 — снимаем его устаревший sentinel с awg0
    # (иначе старый DROP «не через awg0» душил бы трафик списка через awg1)
    if [[ "$table_iface" == "$SG_IFACE" ]]; then
        drop_stale_sentinel "$ipset_name" "$AWG_IFACE"
    fi

    log "Sentinel DROP: $ipset_name не через $table_iface..."
    ensure_fwd_drop -m set --match-set "$ipset_name" dst ! -o "$table_iface"
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

# ── Туннельная часть ──────────────────────────────────────────────────────────

setup_tunnel() {
    local iface="$1" mark="$2" table="$3" priority="$4" label="$5"

    log "Настройка ip route table $table ($label)..."
    if ! ip route show table "$table" | grep -q "default dev $iface"; then
        ip route replace default dev "$iface" table "$table"
    fi

    log "Настройка ip rule fwmark $mark/$FWMARK_MASK → table $table..."
    if ! ip rule show | grep -q "fwmark $mark/$FWMARK_MASK.*lookup $table"; then
        ip rule add fwmark "$mark/$FWMARK_MASK" table "$table" priority "$priority"
    fi

    log "Настройка MASQUERADE для $iface..."
    if ! iptables -t nat -C POSTROUTING -o "$iface" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -o "$iface" -j MASQUERADE
    fi

    log "Настройка FORWARD правил для $iface..."
    if ! iptables -C FORWARD -i "$LAN_IFACE" -o "$iface" -j ACCEPT 2>/dev/null; then
        iptables -A FORWARD -i "$LAN_IFACE" -o "$iface" -j ACCEPT
    fi
    if ! iptables -C FORWARD -i "$iface" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
        iptables -A FORWARD -i "$iface" -o "$LAN_IFACE" -m state --state RELATED,ESTABLISHED -j ACCEPT
    fi

    # Клампинг MSS для TCP через тоннель (причина и расчёт — awg-routing.md, TCPMSS):
    # клиенты LAN согласуют MSS 1460 не зная о тоннеле; MSS 1352 даёт внешний
    # пакет 1420 — проходящий размер на транзите (инцидент 29.09.2026 на awg0).
    log "Настройка TCPMSS clamp (MSS 1352) для $iface..."
    if ! iptables -t mangle -C FORWARD -o "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352 2>/dev/null; then
        iptables -t mangle -A FORWARD -o "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352
    fi
    if ! iptables -t mangle -C FORWARD -i "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352 2>/dev/null; then
        iptables -t mangle -A FORWARD -i "$iface" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1352
    fi
}

if [[ "$AWG_UP" == "yes" ]]; then
    setup_tunnel "$AWG_IFACE" "$FWMARK" "$ROUTE_TABLE" 100 "Франкфурт"
else
    warn "Пропущено (нет $AWG_IFACE): table $ROUTE_TABLE, ip rule, MASQUERADE, FORWARD ACCEPT."
fi

if [[ "$SG_UP" == "yes" ]]; then
    setup_tunnel "$SG_IFACE" "$FWMARK_SG" "$ROUTE_TABLE_SG" 101 "Сингапур"
else
    warn "Пропущено (нет $SG_IFACE): table $ROUTE_TABLE_SG, ip rule, MASQUERADE, FORWARD ACCEPT."
fi

# ── Статические маршруты для SS-серверов ─────────────────────────────────────
# IP SS-серверов заблокированы в РФ — маршрутизируем их через awg0 напрямую
# (трафик ss-local идёт через OUTPUT, не через PREROUTING, поэтому ipset не поможет).
# Endpoint awg1 (Сингапур) при этом идёт через main/WAN — туннели независимы.

if [[ "$AWG_UP" == "yes" ]]; then
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
fi

log "Маршрутизация через AWG применена (fail-closed guard активен)."
