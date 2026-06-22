'''Получение статусов и управление systemd-сервисами через systemctl.'''

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServiceStatus:
    '''Статус одного systemd-сервиса из config.yaml.'''

    key: str
    name: str
    unit: str
    state: str
    description: str
    is_active: bool


def find_systemctl() -> str | None:
    '''Возвращает путь к systemctl или None если не найден.'''
    systemctl_path = shutil.which('systemctl')
    if systemctl_path:
        return systemctl_path
    for path in ['/usr/bin/systemctl', '/bin/systemctl']:
        if Path(path).exists():
            return path
    return None


def get_systemd_service_state(unit: str) -> str:
    '''Возвращает строку состояния юнита: active / inactive / failed / unknown / timeout.'''
    systemctl = find_systemctl()
    if systemctl is None:
        return 'systemctl_not_found'
    try:
        result = subprocess.run(
            [systemctl, 'is-active', unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'},
        )
        return result.stdout.strip() or 'unknown'
    except subprocess.TimeoutExpired:
        return 'timeout'
    except Exception:
        return 'unknown'


def get_service_unit(config: dict, service_name: str) -> str | None:
    '''Возвращает имя юнита для сервиса из конфига или None если сервис не найден.'''
    services = config.get('services', {})
    meta = services.get(service_name)
    if meta is None:
        return None
    if isinstance(meta, str):
        return meta
    if isinstance(meta, dict):
        return meta.get('unit') or meta.get('service') or meta.get('name')
    return None


def get_services_status(config: dict) -> list[ServiceStatus]:
    '''Возвращает список статусов всех сервисов из config.yaml.'''
    services_config = config.get('services', {})
    result = []
    for key, meta in services_config.items():
        if isinstance(meta, str):
            unit = meta
            name = key
            description = ''
        else:
            unit = meta.get('unit', '')
            name = meta.get('name', key)
            description = meta.get('description', '')

        if not unit:
            result.append(ServiceStatus(key=key, name=name, unit='не настроено',
                                        state='not_configured', description=description, is_active=False))
            continue

        state = get_systemd_service_state(unit)
        result.append(ServiceStatus(key=key, name=name, unit=unit,
                                    state=state, description=description, is_active=state == 'active'))
    return result


def restart_service(config: dict, service_name: str) -> subprocess.CompletedProcess:
    '''Перезапускает сервис через sudo systemctl restart.

    Вызывает ValueError если сервис не найден в конфиге.
    '''
    unit = get_service_unit(config, service_name)
    if unit is None:
        raise ValueError(f'Unknown service: {service_name}')
    return subprocess.run(
        ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'restart', unit],
        capture_output=True,
        text=True,
        timeout=30,
    )
