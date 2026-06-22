"""Работа с dnsmasq: статические резервации, аренды DHCP, статус сервиса, ARP."""

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ── Константы ─────────────────────────────────────────────────────────────────

LEASES_FILE = Path('/var/lib/misc/dnsmasq.leases')
STATIC_FILE = Path('/etc/home-router-panel/awg/dnsmasq-static.conf')
DNSMASQ_D = Path('/etc/dnsmasq.d')

_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9\-]{1,63}$')
_IP_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

# Диапазоны последнего октета IP → название группы устройств
_IP_GROUPS: list[tuple[int, int, str]] = [
    (1,   9,   'Сетевое оборудование'),
    (10,  19,  'Компьютеры'),
    (20,  39,  'IoT'),
    (40,  49,  'Медиа'),
    (50,  59,  'Телефоны'),
    (60,  79,  'Динамический пул'),
    (110, 119, 'Камеры'),
    (200, 209, 'Майнеры'),
]
IP_GROUP_NAMES: list[str] = list(dict.fromkeys(n for _, _, n in _IP_GROUPS))


# ── Датаклассы ────────────────────────────────────────────────────────────────

@dataclass
class Lease:
    """Одна запись из файла аренд dnsmasq."""

    expiry: str    # человекочитаемое время истечения или «постоянная»
    ts: int        # unix-timestamp истечения; 0 = бессрочная аренда
    mac: str
    ip: str
    hostname: str
    client_id: str


@dataclass
class StaticEntry:
    """Статическая DHCP-резервация из управляемого файла панели."""

    mac: str       # пустая строка для резерваций по имени устройства
    ip: str
    hostname: str
    mac_from_lease: bool = False  # True если MAC разрешён из файла аренд


# ── Приватные хелперы ──────────────────────────────────────────────────────────

def _test_config() -> tuple[bool, str]:
    """Запускает dnsmasq --test для проверки конфига. Возвращает (ok, вывод)."""
    try:
        result = subprocess.run(
            ['/usr/bin/dnsmasq', '--test'],
            capture_output=True, text=True, timeout=5,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return True, ''  # dnsmasq не найден локально — пропускаем проверку
    except Exception as e:
        return False, str(e)


# ── Валидация ─────────────────────────────────────────────────────────────────

def validate_entry(mac: str, ip: str, hostname: str) -> str | None:
    """Проверяет корректность полей записи. Возвращает строку ошибки или None."""
    mac = mac.strip().lower()
    if mac:
        if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
            return f'Некорректный MAC-адрес: {mac!r}'
    else:
        if not hostname or not hostname.strip():
            return 'Укажите MAC-адрес или имя устройства'
    if ip:
        if not _IP_RE.match(ip.strip()):
            return f'Некорректный IP-адрес: {ip!r}'
        parts = ip.strip().split('.')
        if not all(0 <= int(p) <= 255 for p in parts):
            return f'IP-адрес вне допустимого диапазона: {ip!r}'
    if hostname:
        h = hostname.strip()
        if not _HOSTNAME_RE.match(h):
            bad = [c for c in h if not re.match(r'[a-zA-Z0-9\-]', c)]
            return (
                f'Недопустимые символы в имени: {set(bad)} — '
                f'только латиница, цифры и дефис (без пробелов, кириллицы, скобок)'
            )
    return None


# ── Чтение данных ─────────────────────────────────────────────────────────────

def read_leases() -> list[Lease]:
    """Читает файл аренд dnsmasq, возвращает список отсортированный по IP."""
    if not LEASES_FILE.exists():
        return []
    try:
        leases = []
        for line in LEASES_FILE.read_text(encoding='utf-8').splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ts = 0
            try:
                ts = int(parts[0])
                if ts == 0:
                    expiry = 'постоянная'
                else:
                    expiry = datetime.utcfromtimestamp(ts).strftime('%d.%m %H:%M')
            except ValueError:
                expiry = parts[0]
            mac = parts[1].lower()
            ip = parts[2]
            hostname = parts[3] if parts[3] != '*' else ''
            client_id = parts[4] if len(parts) > 4 else ''
            leases.append(Lease(expiry=expiry, ts=ts, mac=mac, ip=ip, hostname=hostname, client_id=client_id))
        leases.sort(key=lambda l: tuple(int(x) for x in l.ip.split('.')) if l.ip.count('.') == 3 else (0,))
        return leases
    except Exception:
        return []


def read_system_static() -> list[dict]:
    """Читает dhcp-host записи из /etc/dnsmasq.d/*.conf. Только для отображения, не редактируется."""
    entries = []
    if not DNSMASQ_D.exists():
        return entries
    try:
        for conf in sorted(DNSMASQ_D.glob('*.conf')):
            for line in conf.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line.startswith('dhcp-host='):
                    continue
                value = line[len('dhcp-host='):]
                parts = value.split(',')
                mac = parts[0].strip().lower() if parts else ''
                ip = parts[1].strip() if len(parts) > 1 else ''
                hostname = parts[2].strip() if len(parts) > 2 else ''
                if re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
                    entries.append({'mac': mac, 'ip': ip, 'hostname': hostname, 'source': conf.name})
    except Exception:
        pass
    return entries


def read_static() -> list[StaticEntry]:
    """Читает управляемый файл резерваций dnsmasq-static.conf, сортирует по IP."""
    if not STATIC_FILE.exists():
        return []
    try:
        entries = []
        for line in STATIC_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if not line.startswith('dhcp-host='):
                continue
            value = line[len('dhcp-host='):]
            parts = value.split(',')
            first = parts[0].strip()
            if re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', first.lower()):
                mac = first.lower()
                ip = parts[1].strip() if len(parts) > 1 else ''
                hostname = parts[2].strip() if len(parts) > 2 else ''
            else:
                # резервация по имени устройства: dhcp-host=Hostname,IP
                mac = ''
                hostname = first
                ip = parts[1].strip() if len(parts) > 1 else ''
            entries.append(StaticEntry(mac=mac, ip=ip, hostname=hostname))
        entries.sort(key=lambda e: tuple(int(x) for x in e.ip.split('.')) if e.ip.count('.') == 3 else (0,))
        return entries
    except Exception:
        return []


# ── Запись и изменение резерваций ─────────────────────────────────────────────

def write_static(entries: list[StaticEntry]) -> tuple[bool, str]:
    """Записывает список резерваций в файл. Проверяет конфиг через dnsmasq --test, при ошибке откатывает."""
    STATIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# Home Router Panel — DHCP static reservations', '# dhcp-host=MAC,IP,hostname', '']
    for e in entries:
        if e.mac:
            parts = [e.mac, e.ip]
            if e.hostname:
                parts.append(e.hostname)
        else:
            parts = [e.hostname, e.ip]
        lines.append('dhcp-host=' + ','.join(parts))
    lines.append('')
    backup = STATIC_FILE.read_text(encoding='utf-8') if STATIC_FILE.exists() else None
    STATIC_FILE.write_text('\n'.join(lines), encoding='utf-8')
    ok, msg = _test_config()
    if not ok:
        if backup is not None:
            STATIC_FILE.write_text(backup, encoding='utf-8')
        else:
            STATIC_FILE.unlink(missing_ok=True)
        return False, f'dnsmasq --test провалился, файл откатан: {msg}'
    return True, ''


def add_static(mac: str, ip: str, hostname: str) -> tuple[bool, str]:
    """Добавляет или обновляет резервацию. Возвращает (ok, ошибка_или_пусто)."""
    mac = mac.strip().lower()
    hostname = hostname.strip()
    err = validate_entry(mac, ip, hostname)
    if err:
        return False, err
    entries = read_static()
    if mac:
        for e in entries:
            if e.mac == mac:
                e.ip = ip.strip()
                e.hostname = hostname
                return write_static(entries)
    else:
        for e in entries:
            if not e.mac and e.hostname == hostname:
                e.ip = ip.strip()
                return write_static(entries)
    entries.append(StaticEntry(mac=mac, ip=ip.strip(), hostname=hostname))
    return write_static(entries)


def remove_static(mac: str, hostname: str = '') -> tuple[bool, str]:
    """Удаляет резервацию по MAC или имени устройства. Возвращает (ok, ошибка_или_пусто)."""
    mac = mac.strip().lower()
    hostname = hostname.strip()
    entries = read_static()
    if mac:
        new = [e for e in entries if e.mac != mac]
    elif hostname:
        new = [e for e in entries if not (not e.mac and e.hostname == hostname)]
    else:
        return False, 'Не указан MAC или имя'
    if len(new) == len(entries):
        return False, 'Запись не найдена'
    return write_static(new)


# ── Управление сервисом ────────────────────────────────────────────────────────

def get_dnsmasq_state() -> str:
    """Возвращает строку состояния сервиса dnsmasq (active / inactive / failed / unknown)."""
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', 'dnsmasq'],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def reload_dnsmasq() -> tuple[bool, str]:
    """Отправляет SIGHUP dnsmasq (применяет конфиг без обрыва аренд). Возвращает (ok, сообщение)."""
    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'reload', 'dnsmasq'],
            capture_output=True, text=True, timeout=10,
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception as e:
        return False, str(e)


def restart_dnsmasq() -> tuple[bool, str]:
    """Полный перезапуск dnsmasq. Сбрасывает все аренды. Возвращает (ok, сообщение)."""
    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'restart', 'dnsmasq'],
            capture_output=True, text=True, timeout=15,
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception as e:
        return False, str(e)


# ── Группировка по диапазонам IP ──────────────────────────────────────────────

def get_ip_group(ip: str) -> str:
    """Возвращает название группы по последнему октету IP или пустую строку."""
    try:
        last = int(ip.rsplit('.', 1)[-1])
    except (ValueError, IndexError):
        return ''
    for lo, hi, name in _IP_GROUPS:
        if lo <= last <= hi:
            return name
    return ''


def group_static_entries(entries: list[StaticEntry]) -> list[dict]:
    """Группирует записи по диапазонам IP. Возвращает список {name, lo, hi, entries}."""
    buckets: dict[str, list[StaticEntry]] = {n: [] for n in IP_GROUP_NAMES}
    ungrouped: list[StaticEntry] = []
    for e in entries:
        g = get_ip_group(e.ip)
        if g and g != 'Динамический пул':
            buckets[g].append(e)
        else:
            ungrouped.append(e)
    result = []
    for name in IP_GROUP_NAMES:
        if name == 'Динамический пул':
            continue
        lo = min(lo for lo, hi, n in _IP_GROUPS if n == name)
        hi = max(hi for lo, hi, n in _IP_GROUPS if n == name)
        result.append({'name': name, 'lo': lo, 'hi': hi, 'entries': buckets[name]})
    if ungrouped:
        result.append({'name': 'Прочие', 'lo': None, 'hi': None, 'entries': ungrouped})
    return result


# ── Определение онлайн-статуса через ARP ─────────────────────────────────────

def get_arp_online() -> tuple[set[str], set[str]]:
    """Возвращает (online_macs, online_ips) из ARP-таблицы интерфейса enp2s0.

    Устройство считается онлайн если имеет lladdr и состояние не FAILED.
    Состояния REACHABLE / STALE / DELAY / PROBE — онлайн.
    После отключения запись переходит в FAILED примерно за 1–3 минуты.
    При ошибке вызова ip возвращает два пустых множества.
    """
    try:
        result = subprocess.run(
            ['/usr/sbin/ip', 'neigh', 'show', 'dev', 'enp2s0'],
            capture_output=True, text=True, timeout=5,
        )
        macs: set[str] = set()
        ips: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts or 'lladdr' not in parts or 'FAILED' in parts:
                continue
            ip = parts[0]
            idx = parts.index('lladdr')
            if idx + 1 < len(parts):
                macs.add(parts[idx + 1].lower())
                ips.add(ip)
        return macs, ips
    except Exception:
        return set(), set()
