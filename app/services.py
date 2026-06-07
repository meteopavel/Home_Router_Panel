import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServiceStatus:
    key: str
    name: str
    unit: str
    state: str
    description: str
    is_active: bool


def find_systemctl() -> str | None:
    systemctl_path = shutil.which("systemctl")

    if systemctl_path:
        return systemctl_path

    fallback_paths = [
        "/usr/bin/systemctl",
        "/bin/systemctl",
    ]

    for path in fallback_paths:
        if Path(path).exists():
            return path

    return None


def get_systemd_service_state(unit: str) -> str:
    systemctl = find_systemctl()

    if systemctl is None:
        return "systemctl_not_found"

    try:
        result = subprocess.run(
            [systemctl, "is-active", unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env={
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C",
            },
        )

        state = result.stdout.strip()

        if state:
            return state

        stderr = result.stderr.strip()

        if stderr:
            return "unknown"

        return "unknown"

    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "unknown"


def get_services_status(config: dict) -> list[ServiceStatus]:
    services_config = config.get("services", {})

    services_map = {
        "zapret": {
            "name": "zapret",
            "description": "Сервис фильтрации/обхода блокировок zapret",
        },
        "amnezia": {
            "name": "Amnezia VPN",
            "description": "WireGuard/Amnezia VPN tunnel",
        },
    }

    result = []

    for key, meta in services_map.items():
        unit = services_config.get(key)

        if not unit:
            result.append(
                ServiceStatus(
                    key=key,
                    name=meta["name"],
                    unit="не настроено",
                    state="not_configured",
                    description=meta["description"],
                    is_active=False,
                )
            )
            continue

        state = get_systemd_service_state(unit)

        result.append(
            ServiceStatus(
                key=key,
                name=meta["name"],
                unit=unit,
                state=state,
                description=meta["description"],
                is_active=state == "active",
            )
        )

    return result


def get_service_unit(config: dict, service_name: str) -> str | None:
    services = config.get("services", {})
    service_config = services.get(service_name)

    if service_config is None:
        return None

    if isinstance(service_config, str):
        return service_config

    if isinstance(service_config, dict):
        return (
            service_config.get("unit")
            or service_config.get("service")
            or service_config.get("name")
        )

    return None


def restart_service(config: dict, service_name: str) -> subprocess.CompletedProcess:
    unit = get_service_unit(config, service_name)

    if unit is None:
        raise ValueError(f"Unknown service: {service_name}")

    return subprocess.run(
        ["sudo", "systemctl", "restart", unit],
        capture_output=True,
        text=True,
        timeout=30,
    )