import re
import subprocess
from pathlib import Path
from typing import Optional

SUDO = "/usr/bin/sudo"
HELPER = "/usr/local/sbin/home-router-awg-config"
AWG_CONFIG_DIR = Path("/etc/home-router-panel/awg")

LIST_FILES = {
    "tg_nets": AWG_CONFIG_DIR / "tg_nets.txt",
    "figma_domains": AWG_CONFIG_DIR / "figma_domains.txt",
    "claude_domains": AWG_CONFIG_DIR / "claude_domains.txt",
    "vpn_device_macs": AWG_CONFIG_DIR / "vpn_device_macs.txt",
}

LIST_META = {
    "tg_nets": {
        "title": "Telegram сети",
        "hint": "IPv4 адреса и CIDR-блоки, по одному на строку",
    },
    "figma_domains": {
        "title": "Figma домены",
        "hint": "Домены, чьи IP резолвятся и идут через VPN",
    },
    "claude_domains": {
        "title": "Claude / Anthropic домены",
        "hint": "Домены, чьи IP резолвятся и идут через VPN",
    },
    "vpn_device_macs": {
        "title": "Устройства по MAC",
        "hint": "xx:xx:xx:xx:xx:xx — можно добавить # комментарий",
    },
}


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


def get_lan_devices() -> list[dict]:
    result = _run_helper("lan-neigh")
    if result.returncode != 0:
        return []
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
            devices.append({"ip": ip, "mac": mac, "state": state})
    return devices


def check_route(target: str) -> str:
    if not re.match(r'^[a-zA-Z0-9.\-_]+$', target):
        return "Некорректный формат — только домен или IP"
    result = _run_helper("check-route", target, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or "Ошибка")


def read_awg_list(name: str) -> str:
    path = LIST_FILES.get(name)
    if path is None:
        raise ValueError(f"Unknown list: {name}")
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except PermissionError:
        return f"# Нет доступа к {path}\n# chown <panel-user>: {path}"


def write_awg_list(name: str, content: str) -> None:
    path = LIST_FILES.get(name)
    if path is None:
        raise ValueError(f"Unknown list: {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_suffix(".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")


def add_mac_to_vpn(mac: str) -> bool:
    mac = mac.strip().lower()
    if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
        return False
    path = LIST_FILES["vpn_device_macs"]
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    for line in current.splitlines():
        if line.split("#")[0].strip().lower() == mac:
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current.rstrip("\n") + f"\n{mac}\n", encoding="utf-8")
    return True
