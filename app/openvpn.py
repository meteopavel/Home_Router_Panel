"""OpenVPN: статус сервиса openvpn@mailganer, управление, список разрешённых MAC."""

import subprocess
from pathlib import Path

CONF_DIR = Path('/etc/home-router-panel/openvpn')
VPN_MACS_FILE = CONF_DIR / 'vpn_device_macs.txt'
SERVICE_UNIT = 'openvpn@mailganer'
HELPER = '/usr/local/sbin/home-router-openvpn-routing'


def get_openvpn_status() -> dict:
    """Возвращает состояние сервиса openvpn@mailganer и наличие интерфейса tun0."""
    result = {'service_state': 'unknown', 'tun0_up': False, 'service_since': ''}
    try:
        r = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', SERVICE_UNIT],
            capture_output=True, text=True, timeout=3, check=False,
        )
        result['service_state'] = r.stdout.strip() or 'unknown'
    except Exception:
        pass

    try:
        r = subprocess.run(
            ['/sbin/ip', 'link', 'show', 'tun0'],
            capture_output=True, text=True, timeout=3, check=False,
        )
        result['tun0_up'] = r.returncode == 0 and 'UP' in r.stdout
    except Exception:
        pass

    try:
        r = subprocess.run(
            ['/usr/bin/systemctl', 'show', SERVICE_UNIT,
             '--property=ActiveEnterTimestampMonotonic,ActiveEnterTimestamp'],
            capture_output=True, text=True, timeout=3, check=False,
        )
        for line in r.stdout.splitlines():
            if line.startswith('ActiveEnterTimestamp=') and not line.endswith('='):
                result['service_since'] = line.split('=', 1)[1].strip()
                break
    except Exception:
        pass

    return result


def openvpn_action(action: str) -> tuple[bool, str]:
    """Выполняет start/stop/restart для openvpn@mailganer через sudo."""
    if action not in ('start', 'stop', 'restart'):
        return False, f'Недопустимое действие: {action}'
    try:
        r = subprocess.run(
            ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', action, SERVICE_UNIT],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if r.returncode == 0:
            return True, ''
        return False, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, 'Timeout'
    except Exception as e:
        return False, str(e)


def read_vpn_macs() -> list[str]:
    """Читает список MAC-адресов из vpn_device_macs.txt."""
    if not VPN_MACS_FILE.exists():
        return []
    lines = VPN_MACS_FILE.read_text(encoding='utf-8').splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]


def write_vpn_macs(macs: list[str]) -> None:
    """Сохраняет список MAC-адресов в vpn_device_macs.txt."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    VPN_MACS_FILE.write_text('\n'.join(sorted(macs)) + '\n', encoding='utf-8')


def apply_routing() -> tuple[bool, str]:
    """Запускает скрипт маршрутизации через sudo."""
    try:
        r = subprocess.run(
            ['/usr/bin/sudo', '-n', HELPER, 'apply'],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, 'Timeout'
    except Exception as e:
        return False, str(e)


def helper_available() -> bool:
    return Path(HELPER).exists()


def _fmt_bytes(n: int) -> str:
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024:
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024
    return f'{n:.1f} TiB'


def get_tun0_traffic() -> dict:
    """Читает статистику tun0 из vnstat."""
    empty = {'available': False, 'has_data': False,
             'five_rx': '—', 'five_tx': '—',
             'hour_rx': '—', 'hour_tx': '—',
             'today_rx': '—', 'today_tx': '—',
             'month_rx': '—', 'month_tx': '—',
             'total_rx': '—', 'total_tx': '—'}
    try:
        r = subprocess.run(
            ['/usr/bin/vnstat', '-i', 'tun0', '--json'],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode != 0:
            return empty
        data = __import__('json').loads(r.stdout)
        iface = data['interfaces'][0]['traffic']

        def last(entries, n=1):
            rx = tx = 0
            for e in entries[-n:]:
                rx += e.get('rx', 0)
                tx += e.get('tx', 0)
            return rx, tx

        total_rx = iface['total']['rx']
        total_tx = iface['total']['tx']
        five_rx, five_tx = last(iface.get('fiveminute', []))
        hour_rx, hour_tx = last(iface.get('hour', []))
        today_rx, today_tx = last(iface.get('day', []))
        month_rx, month_tx = last(iface.get('month', []))

        has_data = total_rx + total_tx > 0
        return {
            'available': True,
            'has_data': has_data,
            'five_rx':  _fmt_bytes(five_rx)  if five_rx  else '—',
            'five_tx':  _fmt_bytes(five_tx)  if five_tx  else '—',
            'hour_rx':  _fmt_bytes(hour_rx)  if hour_rx  else '—',
            'hour_tx':  _fmt_bytes(hour_tx)  if hour_tx  else '—',
            'today_rx': _fmt_bytes(today_rx) if today_rx else '—',
            'today_tx': _fmt_bytes(today_tx) if today_tx else '—',
            'month_rx': _fmt_bytes(month_rx) if month_rx else '—',
            'month_tx': _fmt_bytes(month_tx) if month_tx else '—',
            'total_rx': _fmt_bytes(total_rx),
            'total_tx': _fmt_bytes(total_tx),
        }
    except Exception:
        return empty
