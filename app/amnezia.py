"""Управление AmneziaWG: конфигурация списков, статус и контроль AWG, LAN-устройства."""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional


# ── Константы ─────────────────────────────────────────────────────────────────

SUDO = '/usr/bin/sudo'
HELPER = '/usr/local/sbin/home-router-awg-config'
AWG_CONFIG_DIR = Path('/etc/home-router-panel/awg')
LISTS_CONFIG_FILE = AWG_CONFIG_DIR / 'lists_config.json'
DNSMASQ_LEASES = Path('/var/lib/misc/dnsmasq.leases')

_DEFAULT_LISTS = [
    {'key': 'tg_nets',        'title': 'Telegram сети',               'hint': 'IPv4 адреса и CIDR-блоки, по одному на строку'},
    {'key': 'figma_domains',  'title': 'Figma домены',                'hint': 'Домены, чьи IP резолвятся и идут через VPN'},
    {'key': 'claude_domains', 'title': 'Claude / Anthropic домены',   'hint': 'Домены, чьи IP резолвятся и идут через VPN'},
    {'key': 'bebra_domains',  'title': 'Bebra домены',                'hint': 'Домены, чьи IP резолвятся и идут через VPN'},
    {'key': 'ss_server_ips',  'title': 'SS-серверы (прямой маршрут)', 'hint': 'IP Shadowsocks-серверов — маршрутизируются через awg0 напрямую (не через ipset)'},
    {'key': 'vpn_device_macs','title': 'Устройства по MAC',           'hint': 'xx:xx:xx:xx:xx:xx — можно добавить # комментарий'},
]

_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


# ── Приватные хелперы ──────────────────────────────────────────────────────────

def _run_helper(*args, timeout: int = 15) -> subprocess.CompletedProcess:
    """Запускает home-router-awg-config через sudo. Возвращает CompletedProcess-подобный объект."""
    try:
        return subprocess.run(
            [SUDO, '-n', HELPER] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        class _R:
            returncode = 127
            stdout = ''
            stderr = f'Helper не найден: {HELPER}. Установите скрипт из scripts/.'
        return _R()
    except subprocess.TimeoutExpired:
        class _R:
            returncode = 1
            stdout = ''
            stderr = 'Timeout при вызове helper'
        return _R()


def _list_path(name: str) -> Path:
    """Возвращает путь к файлу списка. Вызывает ValueError если ключ не зарегистрирован."""
    lists = load_lists_config()
    if not any(item['key'] == name for item in lists):
        raise ValueError(f'Unknown list: {name}')
    return AWG_CONFIG_DIR / f'{name}.txt'


def _read_dnsmasq_leases() -> dict[str, str]:
    """Читает файл аренд dnsmasq, возвращает словарь MAC → hostname."""
    if not DNSMASQ_LEASES.exists():
        return {}
    try:
        result = {}
        for line in DNSMASQ_LEASES.read_text(encoding='utf-8').splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mac = parts[1].lower()
                hostname = parts[3] if parts[3] != '*' else ''
                if hostname:
                    result[mac] = hostname
        return result
    except Exception:
        return {}


# ── Управление метаданными списков ────────────────────────────────────────────

def load_lists_config() -> list[dict]:
    """Читает lists_config.json. Возвращает дефолтный список если файл отсутствует или повреждён."""
    if not LISTS_CONFIG_FILE.exists():
        return list(_DEFAULT_LISTS)
    try:
        data = json.loads(LISTS_CONFIG_FILE.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return list(_DEFAULT_LISTS)


def save_lists_config(lists: list[dict]) -> None:
    """Сохраняет метаданные списков в lists_config.json."""
    LISTS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LISTS_CONFIG_FILE.write_text(
        json.dumps(lists, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def get_list_meta() -> dict:
    """Возвращает словарь {ключ: {title, hint}} для использования в шаблонах."""
    return {item['key']: {'title': item['title'], 'hint': item['hint']}
            for item in load_lists_config()}


def create_list(key: str, title: str, hint: str) -> tuple[bool, str]:
    """Создаёт новый список и пустой txt-файл. Возвращает (ok, ошибка_или_пусто)."""
    key = key.strip().lower()
    if not _KEY_RE.match(key):
        return False, 'Ключ: только строчные буквы, цифры и _, начинается с буквы, до 32 символов'
    title = title.strip()
    if not title:
        return False, 'Название обязательно'
    lists = load_lists_config()
    if any(item['key'] == key for item in lists):
        return False, f"Список '{key}' уже существует"
    lists.append({'key': key, 'title': title, 'hint': hint.strip()})
    save_lists_config(lists)
    path = AWG_CONFIG_DIR / f'{key}.txt'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    return True, ''


def update_list_meta(key: str, title: str, hint: str, new_key: str = '') -> tuple[bool, str]:
    """Обновляет название/подсказку списка, при необходимости переименовывает ключ и файл."""
    title = title.strip()
    if not title:
        return False, 'Название обязательно'
    new_key = new_key.strip() or key
    if new_key != key:
        if not _KEY_RE.match(new_key):
            return False, 'Ключ: только строчные буквы, цифры и _, начинается с буквы, до 32 символов'
    lists = load_lists_config()
    if new_key != key and any(item['key'] == new_key for item in lists):
        return False, f"Ключ '{new_key}' уже занят"
    for item in lists:
        if item['key'] == key:
            item['key'] = new_key
            item['title'] = title
            item['hint'] = hint.strip()
            save_lists_config(lists)
            if new_key != key:
                old_path = AWG_CONFIG_DIR / f'{key}.txt'
                new_path = AWG_CONFIG_DIR / f'{new_key}.txt'
                if old_path.exists():
                    old_path.rename(new_path)
            return True, ''
    return False, f"Список '{key}' не найден"


def reorder_lists(keys: list[str]) -> None:
    """Переставляет списки в lists_config.json согласно переданному порядку ключей."""
    lists = load_lists_config()
    by_key = {item['key']: item for item in lists}
    reordered = [by_key[k] for k in keys if k in by_key]
    # Списки, которых нет в keys — добавляем в конец
    present = set(keys)
    reordered += [item for item in lists if item['key'] not in present]
    save_lists_config(reordered)


def delete_list(key: str) -> tuple[bool, str]:
    """Удаляет список из конфига и переименовывает файл в .txt.deleted."""
    lists = load_lists_config()
    new_lists = [item for item in lists if item['key'] != key]
    if len(new_lists) == len(lists):
        return False, f"Список '{key}' не найден"
    save_lists_config(new_lists)
    path = AWG_CONFIG_DIR / f'{key}.txt'
    if path.exists():
        path.rename(path.with_suffix('.txt.deleted'))
    return True, ''


# ── Файловые операции со списками AWG ─────────────────────────────────────────

def read_awg_list(name: str) -> str:
    """Читает содержимое txt-файла списка. Возвращает пустую строку если файл не существует."""
    path = _list_path(name)
    if not path.exists():
        return ''
    try:
        return path.read_text(encoding='utf-8')
    except PermissionError:
        return f'# Нет доступа к {path}\n# chown <panel-user>: {path}'


def write_awg_list(name: str, content: str) -> None:
    """Записывает содержимое в txt-файл списка, сохраняет .bak-резервную копию."""
    path = _list_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_suffix('.bak').write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    path.write_text(content.replace('\r\n', '\n').replace('\r', '\n'), encoding='utf-8')


def add_mac_to_vpn(mac: str) -> bool:
    """Добавляет MAC-адрес в vpn_device_macs.txt. Возвращает False при некорректном MAC."""
    mac = mac.strip().lower()
    if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
        return False
    path = AWG_CONFIG_DIR / 'vpn_device_macs.txt'
    current = path.read_text(encoding='utf-8') if path.exists() else ''
    for line in current.splitlines():
        if line.split('#')[0].strip().lower() == mac:
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current.rstrip('\n') + f'\n{mac}\n', encoding='utf-8')
    return True


# ── Статус и управление AWG ───────────────────────────────────────────────────

def get_awg_status() -> dict:
    """Возвращает словарь со статусом AWG-сервиса и интерфейса от helper-скрипта."""
    result = _run_helper('status')
    status: dict = {
        'available': result.returncode == 0,
        'error': result.stderr.strip() if result.returncode != 0 else None,
    }
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                status[k.strip()] = v.strip()
    return status


def get_awg_show() -> Optional[str]:
    """Возвращает вывод awg show awg0 или None если helper недоступен."""
    result = _run_helper('awg-show')
    return result.stdout.strip() if result.returncode == 0 else None


def run_awg_action(action: str) -> tuple[bool, str]:
    """Выполняет одно из допустимых действий: start / stop / restart / apply."""
    allowed = {'start', 'stop', 'restart', 'apply'}
    if action not in allowed:
        return False, 'Неизвестное действие'
    result = _run_helper(action)
    ok = result.returncode == 0
    msg = (result.stdout.strip() or result.stderr.strip()) if not ok else result.stdout.strip()
    return ok, msg


def get_diagnostics() -> Optional[str]:
    """Возвращает диагностический вывод от helper-скрипта или сообщение об ошибке."""
    result = _run_helper('diagnostics', timeout=10)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


# ── LAN-устройства и проверка маршрутов ──────────────────────────────────────

def get_lan_devices() -> list[dict]:
    """Возвращает список {ip, mac, state, hostname} из ARP-таблицы через helper."""
    result = _run_helper('lan-neigh')
    if result.returncode != 0:
        return []
    leases = _read_dnsmasq_leases()
    devices = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ip = parts[0]
        mac = None
        state = 'UNKNOWN'
        for i, part in enumerate(parts):
            if part == 'lladdr' and i + 1 < len(parts):
                mac = parts[i + 1]
            if part in ('REACHABLE', 'STALE', 'FAILED', 'DELAY', 'PROBE', 'NOARP', 'PERMANENT'):
                state = part
        if mac:
            hostname = leases.get(mac.lower(), '')
            devices.append({'ip': ip, 'mac': mac, 'state': state, 'hostname': hostname})
    return devices


def check_route(target: str) -> str:
    """Проверяет маршрут для домена или IP через helper. Возвращает текстовый вывод."""
    if not re.match(r'^[a-zA-Z0-9.\-_]+$', target):
        return 'Некорректный формат — только домен или IP'
    result = _run_helper('check-route', target, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or 'Ошибка')


def _fmt_bytes(n: int) -> str:
    """Форматирует байты в читаемый вид: B / KiB / MiB / GiB."""
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024:
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} {unit}'
        n /= 1024
    return f'{n:.1f} TiB'


def get_awg_traffic() -> dict:
    """Читает статистику awg0 из vnstat. Возвращает dict с полями для шаблона."""
    empty = {'available': False, 'total_rx': '—', 'total_tx': '—',
             'today_rx': '—', 'today_tx': '—',
             'hour_rx': '—', 'hour_tx': '—',
             'month_rx': '—', 'month_tx': '—'}
    try:
        r = subprocess.run(
            ['vnstat', '-i', 'awg0', '--json'],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode != 0:
            return empty
        data = json.loads(r.stdout)
        iface = data['interfaces'][0]['traffic']

        def day_sum(days, n=1):
            rx = tx = 0
            for d in days[-n:]:
                rx += d.get('rx', 0)
                tx += d.get('tx', 0)
            return rx, tx

        total_rx = iface['total']['rx']
        total_tx = iface['total']['tx']

        today_days = iface.get('day', [])
        today_rx, today_tx = day_sum(today_days, 1)

        hours = iface.get('hour', [])
        hour_rx, hour_tx = day_sum(hours, 1)

        months = iface.get('month', [])
        month_rx, month_tx = day_sum(months, 1)

        has_data = total_rx + total_tx > 0

        return {
            'available': True,
            'has_data': has_data,
            'total_rx': _fmt_bytes(total_rx),
            'total_tx': _fmt_bytes(total_tx),
            'today_rx': _fmt_bytes(today_rx) if today_rx else '—',
            'today_tx': _fmt_bytes(today_tx) if today_tx else '—',
            'hour_rx': _fmt_bytes(hour_rx) if hour_rx else '—',
            'hour_tx': _fmt_bytes(hour_tx) if hour_tx else '—',
            'month_rx': _fmt_bytes(month_rx) if month_rx else '—',
            'month_tx': _fmt_bytes(month_tx) if month_tx else '—',
        }
    except Exception:
        return empty
