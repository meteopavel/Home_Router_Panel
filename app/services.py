import subprocess
from dataclasses import dataclass


@dataclass
class ServiceStatus:
    key: str
    name: str
    unit: str
    state: str
    description: str
    is_active: bool


def get_systemd_service_state(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

        state = result.stdout.strip()

        if state:
            return state

        return "unknown"

    except FileNotFoundError:
        return "systemctl_not_found"
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