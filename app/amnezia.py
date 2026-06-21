import json
import re
import subprocess
from pathlib import Path
from typing import Optional

SUDO = "/usr/bin/sudo"
HELPER = "/usr/local/sbin/home-router-awg-config"
AWG_CONFIG_DIR = Path("/etc/home-router-panel/awg")
LISTS_CONFIG_FILE = AWG_CONFIG_DIR / "lists_config.json"

_DEFAULT_LISTS = [
    {"key": "tg_nets",        "title": "Telegram сети",              "hint": "IPv4 адреса и CIDR-блоки, по одному на строку"},
    {"key": "figma_domains",  "title": "Figma домены",               "hint": "Домены, чьи IP резолвятся и идут через VPN"},
    {"key": "claude_domains", "title": "Claude / Anthropic домены",  "hint": "Домены, чьи IP резолвятся и идут через VPN"},
    {"key": "bebra_domains",  "title": "Bebra домены",               "hint": "Домены, чьи IP резолвятся и идут через VPN"},
    {"key": "ss_server_ips",  "title": "SS-серверы (прямой маршрут)", "hint": "IP Shadowsocks-серверов — маршрутизируются через awg0 напрямую (не через ipset)"},
    {"key": "vpn_device_macs","title": "Устройства по MAC",          "hint": "xx:xx:xx:xx:xx:xx — можно добавить # комментарий"},
]

_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


def load_lists_config() -> list[dict]:
    """Return list of {key, title, hint} dicts. Falls back to defaults if file absent."""
    if not LISTS_CONFIG_FILE.exists():
        return list(_DEFAULT_LISTS)
    try:
        data = json.loads(LISTS_CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return list(_DEFAULT_LISTS)


def save_lists_config(lists: list[dict]) -> None:
    LISTS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LISTS_CONFIG_FILE.write_text(
        json.dumps(lists, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_list_meta() -> dict:
    """Return {key: {title, hint}} dict for template use."""
    return {item["key"]: {"title": item["title"], "hint": item["hint"]}
            for item in load_lists_config()}


def create_list(key: str, title: str, hint: str) -> tuple[bool, str]:
    key = key.strip().lower()
    if not _KEY_RE.match(key):
        return False, "Ключ: только строчные буквы, цифры и _, начинается с буквы, до 32 символов"
    title = title.strip()
    if not title:
        return False, "Название обязательно"
    lists = load_lists_config()
    if any(item["key"] == key for item in lists):
        return False, f"Список '{key}' уже существует"
    lists.append({"key": key, "title": title, "hint": hint.strip()})
    save_lists_config(lists)
    path = AWG_CONFIG_DIR / f"{key}.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return True, ""


def update_list_meta(key: str, title: str, hint: str) -> tuple[bool, str]:
    title = title.strip()
    if not title:
        return False, "Название обязательно"
    lists = load_lists_config()
    for item in lists:
        if item["key"] == key:
            item["title"] = title
            item["hint"] = hint.strip()
            save_lists_config(lists)
            return True, ""
    return False, f"Список '{key}' не найден"


def delete_list(key: str) -> tuple[bool, str]:
    lists = load_lists_config()
    new_lists = [item for item in lists if item["key"] != key]
    if len(new_lists) == len(lists):
        return False, f"Список '{key}' не найден"
    save_lists_config(new_lists)
    path = AWG_CONFIG_DIR / f"{key}.txt"
    if path.exists():
        bak = path.with_suffix(".txt.deleted")
        path.rename(bak)
    return True, ""


def _run_helper(*args, timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [SUDO, "-n", HELPER] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        class _R:
            returncode = 127
            stdout = ""
            stderr = f"Helper не найден: {HELPER}. Установите скрипт из scripts/."
        return _R()
    except subprocess.TimeoutExpired:
        class _R:
            returncode = 1
            stdout = ""
            stderr = "Timeout при вызове helper"
        return _R()


def get_awg_status() -> dict:
    result = _run_helper("status")
    status: dict = {
        "available": result.returncode == 0,
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                status[k.strip()] = v.strip()
    return status


def get_awg_show() -> Optional[str]:
    result = _run_helper("awg-show")
    return result.stdout.strip() if result.returncode == 0 else None


def run_awg_action(action: str) -> tuple[bool, str]:
    allowed = {"start", "stop", "restart", "apply"}
    if action not in allowed:
        return False, "Неизвестное действие"
    result = _run_helper(action)
    ok = result.returncode == 0
    msg = (result.stdout.strip() or result.stderr.strip()) if not ok else result.stdout.strip()
    return ok, msg


def get_diagnostics() -> Optional[str]:
    result = _run_helper("diagnostics", timeout=10)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


DNSMASQ_LEASES = Path("/var/lib/misc/dnsmasq.leases")


def _read_dnsmasq_leases() -> dict[str, str]:
    """Return MAC→hostname map from dnsmasq leases file."""
    if not DNSMASQ_LEASES.exists():
        return {}
    try:
        result = {}
        for line in DNSMASQ_LEASES.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mac = parts[1].lower()
                hostname = parts[3] if parts[3] != "*" else ""
                if hostname:
                    result[mac] = hostname
        return result
    except Exception:
        return {}


def get_lan_devices() -> list[dict]:
    result = _run_helper("lan-neigh")
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
        state = "UNKNOWN"
        for i, part in enumerate(parts):
            if part == "lladdr" and i + 1 < len(parts):
                mac = parts[i + 1]
            if part in ("REACHABLE", "STALE", "FAILED", "DELAY", "PROBE", "NOARP", "PERMANENT"):
                state = part
        if mac:
            hostname = leases.get(mac.lower(), "")
            devices.append({"ip": ip, "mac": mac, "state": state, "hostname": hostname})
    return devices


def check_route(target: str) -> str:
    if not re.match(r'^[a-zA-Z0-9.\-_]+$', target):
        return "Некорректный формат — только домен или IP"
    result = _run_helper("check-route", target, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or "Ошибка")


def _list_path(name: str) -> Path:
    lists = load_lists_config()
    if not any(item["key"] == name for item in lists):
        raise ValueError(f"Unknown list: {name}")
    return AWG_CONFIG_DIR / f"{name}.txt"


def read_awg_list(name: str) -> str:
    path = _list_path(name)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except PermissionError:
        return f"# Нет доступа к {path}\n# chown <panel-user>: {path}"


def write_awg_list(name: str, content: str) -> None:
    path = _list_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_suffix(".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")


def add_mac_to_vpn(mac: str) -> bool:
    mac = mac.strip().lower()
    if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
        return False
    path = AWG_CONFIG_DIR / "vpn_device_macs.txt"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    for line in current.splitlines():
        if line.split("#")[0].strip().lower() == mac:
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current.rstrip("\n") + f"\n{mac}\n", encoding="utf-8")
    return True
