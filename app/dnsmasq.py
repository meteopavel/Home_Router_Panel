import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LEASES_FILE = Path("/var/lib/misc/dnsmasq.leases")
STATIC_FILE = Path("/etc/home-router-panel/awg/dnsmasq-static.conf")

# Valid dnsmasq hostname: ASCII letters, digits, hyphens only. No spaces, no unicode.
_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9\-]{1,63}$')
_IP_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')


def validate_entry(mac: str, ip: str, hostname: str) -> str | None:
    """Return error string if invalid, None if ok."""
    mac = mac.strip().lower()
    if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
        return f"Некорректный MAC-адрес: {mac!r}"
    if ip:
        if not _IP_RE.match(ip.strip()):
            return f"Некорректный IP-адрес: {ip!r}"
        parts = ip.strip().split(".")
        if not all(0 <= int(p) <= 255 for p in parts):
            return f"IP-адрес вне допустимого диапазона: {ip!r}"
    if hostname:
        h = hostname.strip()
        if not _HOSTNAME_RE.match(h):
            bad = [c for c in h if not re.match(r'[a-zA-Z0-9\-]', c)]
            return (
                f"Недопустимые символы в имени: {set(bad)} — "
                f"только латиница, цифры и дефис (без пробелов, кириллицы, скобок)"
            )
    return None


def _test_config() -> tuple[bool, str]:
    """Run dnsmasq --test to validate current config. Returns (ok, output)."""
    try:
        result = subprocess.run(
            ["/usr/bin/dnsmasq", "--test"],
            capture_output=True, text=True, timeout=5,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return True, ""  # dnsmasq not in PATH locally — skip test
    except Exception as e:
        return False, str(e)


@dataclass
class Lease:
    expiry: str
    mac: str
    ip: str
    hostname: str
    client_id: str


@dataclass
class StaticEntry:
    mac: str
    ip: str
    hostname: str


def read_leases() -> list[Lease]:
    if not LEASES_FILE.exists():
        return []
    try:
        leases = []
        for line in LEASES_FILE.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                ts = int(parts[0])
                if ts == 0:
                    expiry = "постоянная"
                else:
                    expiry = datetime.utcfromtimestamp(ts).strftime("%d.%m %H:%M")
            except ValueError:
                expiry = parts[0]
            mac = parts[1].lower()
            ip = parts[2]
            hostname = parts[3] if parts[3] != "*" else ""
            client_id = parts[4] if len(parts) > 4 else ""
            leases.append(Lease(expiry=expiry, mac=mac, ip=ip, hostname=hostname, client_id=client_id))
        leases.sort(key=lambda l: tuple(int(x) for x in l.ip.split(".")) if l.ip.count(".") == 3 else (0,))
        return leases
    except Exception:
        return []


DNSMASQ_D = Path("/etc/dnsmasq.d")


def read_system_static() -> list[dict]:
    """Read dhcp-host entries from /etc/dnsmasq.d/*.conf (read-only, for display)."""
    entries = []
    if not DNSMASQ_D.exists():
        return entries
    try:
        for conf in sorted(DNSMASQ_D.glob("*.conf")):
            for line in conf.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line.startswith("dhcp-host="):
                    continue
                value = line[len("dhcp-host="):]
                parts = value.split(",")
                mac = parts[0].strip().lower() if parts else ""
                ip = parts[1].strip() if len(parts) > 1 else ""
                hostname = parts[2].strip() if len(parts) > 2 else ""
                if re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
                    entries.append({"mac": mac, "ip": ip, "hostname": hostname, "source": conf.name})
    except Exception:
        pass
    return entries


def read_static() -> list[StaticEntry]:
    if not STATIC_FILE.exists():
        return []
    try:
        entries = []
        for line in STATIC_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("dhcp-host="):
                continue
            value = line[len("dhcp-host="):]
            parts = value.split(",")
            first = parts[0].strip()
            if re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", first.lower()):
                mac = first.lower()
                ip = parts[1].strip() if len(parts) > 1 else ""
                hostname = parts[2].strip() if len(parts) > 2 else ""
            else:
                # hostname-only entry: dhcp-host=Hostname,IP
                mac = ""
                hostname = first
                ip = parts[1].strip() if len(parts) > 1 else ""
            entries.append(StaticEntry(mac=mac, ip=ip, hostname=hostname))
        entries.sort(key=lambda e: tuple(int(x) for x in e.ip.split(".")) if e.ip.count(".") == 3 else (0,))
        return entries
    except Exception:
        return []


def write_static(entries: list[StaticEntry]) -> tuple[bool, str]:
    """Write static entries. Returns (ok, error_or_empty)."""
    STATIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Home Router Panel — DHCP static reservations", "# dhcp-host=MAC,IP,hostname", ""]
    for e in entries:
        parts = [e.mac, e.ip]
        if e.hostname:
            parts.append(e.hostname)
        lines.append("dhcp-host=" + ",".join(parts))
    lines.append("")
    backup = STATIC_FILE.read_text(encoding="utf-8") if STATIC_FILE.exists() else None
    STATIC_FILE.write_text("\n".join(lines), encoding="utf-8")
    ok, msg = _test_config()
    if not ok:
        if backup is not None:
            STATIC_FILE.write_text(backup, encoding="utf-8")
        else:
            STATIC_FILE.unlink(missing_ok=True)
        return False, f"dnsmasq --test провалился, файл откатан: {msg}"
    return True, ""


def add_static(mac: str, ip: str, hostname: str) -> tuple[bool, str]:
    """Add or update entry. Returns (ok, error_or_empty)."""
    mac = mac.strip().lower()
    err = validate_entry(mac, ip, hostname)
    if err:
        return False, err
    entries = read_static()
    for e in entries:
        if e.mac == mac:
            e.ip = ip.strip()
            e.hostname = hostname.strip()
            return write_static(entries)
    entries.append(StaticEntry(mac=mac, ip=ip.strip(), hostname=hostname.strip()))
    return write_static(entries)


def remove_static(mac: str) -> tuple[bool, str]:
    mac = mac.strip().lower()
    entries = read_static()
    new = [e for e in entries if e.mac != mac]
    if len(new) == len(entries):
        return False, "Запись не найдена"
    return write_static(new)
    return True


def reload_dnsmasq() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "reload", "dnsmasq"],
            capture_output=True, text=True, timeout=10,
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception as e:
        return False, str(e)


def restart_dnsmasq() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "restart", "dnsmasq"],
            capture_output=True, text=True, timeout=15,
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception as e:
        return False, str(e)


def get_dnsmasq_state() -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "dnsmasq"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"
