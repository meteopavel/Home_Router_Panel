"""Маршруты FastAPI: обзор, zapret, AmneziaWG, dnsmasq, бэкап, SSE."""

import asyncio
import json as _json
from pathlib import Path
import subprocess

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dnsmasq import (
    add_static,
    get_arp_online,
    get_dnsmasq_state,
    group_static_entries,
    read_leases,
    read_static,
    read_system_static,
    reload_dnsmasq,
    remove_static,
    restart_dnsmasq,
    LEASES_FILE,
    STATIC_FILE,
)
from app.amnezia import (
    create_list,
    delete_list,
    update_list_meta,
    add_mac_to_vpn,
    check_route,
    get_awg_show,
    get_awg_status,
    get_diagnostics,
    get_lan_devices,
    get_list_meta,
    read_awg_list,
    run_awg_action,
    write_awg_list,
)
from app.config import load_config
from app.hotlists import get_hotlists_config, read_hotlist, write_hotlist
from app.services import get_services_status, restart_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / 'static'
TEMPLATES_DIR = PROJECT_ROOT / 'templates'


app = FastAPI(title='Home Router Panel')

app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get('/')
def index(request: Request):
    """Главная страница: карточки обзора и статусы сервисов."""
    config = load_config()
    services = get_services_status(config)

    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={
            'title': config.get('app', {}).get('title', 'Home Router Panel'),
            'config': config,
            'services': services,
            'active_tab': 'overview',
        },
    )


@app.get('/zapret')
def zapret_view(request: Request):
    """Вкладка zapret: список hotlist-файлов и статус сервиса."""
    config = load_config()
    hotlists = get_hotlists_config(config)
    services = get_services_status(config)
    zapret_service = next((s for s in services if s.key == 'zapret'), None)

    return templates.TemplateResponse(
        request=request,
        name='zapret.html',
        context={
            'title': 'zapret',
            'hotlists': hotlists,
            'zapret_service': zapret_service,
            'active_tab': 'zapret',
        },
    )


@app.get('/hotlists/{name}')
def hotlist_view(name: str):
    """Перенаправляет на страницу редактирования hotlist."""
    return RedirectResponse(url=f'/hotlists/{name}/edit', status_code=302)


@app.get('/hotlists/{name}/edit')
def hotlist_edit_view(request: Request, name: str):
    """Редактирование hotlist-файла zapret."""
    config = load_config()
    hotlist = read_hotlist(config, name)

    if hotlist is None:
        raise HTTPException(status_code=404, detail='Hotlist not found')

    return templates.TemplateResponse(
        request=request,
        name='hotlist_edit.html',
        context={
            'title': f'Редактировать: {hotlist.name}',
            'hotlist': hotlist,
            'active_tab': 'zapret',
        },
    )


@app.post('/hotlists/{name}/edit')
def hotlist_edit_save(request: Request, name: str, content: str = Form(default='')):
    """Сохраняет hotlist и перезапускает zapret."""
    config = load_config()

    try:
        write_hotlist(config, name, content)
    except ValueError:
        raise HTTPException(status_code=404, detail='Hotlist not found')

    restart_error = ''
    try:
        result = restart_service(config, 'zapret')
        if result.returncode != 0:
            restart_error = result.stderr.strip() or result.stdout.strip() or 'zapret не перезапустился'
    except Exception as e:
        restart_error = str(e)

    if restart_error:
        hotlist = read_hotlist(config, name)
        return templates.TemplateResponse(
            request=request,
            name='hotlist_edit.html',
            context={
                'title': f'Редактировать: {hotlist.name}',
                'hotlist': hotlist,
                'active_tab': 'zapret',
                'restart_error': restart_error,
            },
        )

    return RedirectResponse(url=f'/hotlists/{name}/edit?saved=1', status_code=303)


def _parse_vpn_macs(content: str) -> set[str]:
    """Парсит содержимое vpn_device_macs.txt, возвращает множество MAC-адресов (строчные)."""
    result = set()
    for line in content.splitlines():
        mac = line.split('#')[0].strip().lower()
        if mac:
            result.add(mac)
    return result


def _amnezia_context(request: Request, target: str = '', msg: str = '', error: str = '') -> dict:
    """Собирает контекст шаблона amnezia.html: статус AWG, списки, резервации, VPN-MACs."""
    list_meta = get_list_meta()
    check_result = None
    if target:
        check_result = check_route(target)
    vpn_macs_content = read_awg_list('vpn_device_macs') if 'vpn_device_macs' in list_meta else ''
    vpn_macs_selected = _parse_vpn_macs(vpn_macs_content)
    static_entries = read_static()
    leases = read_leases()
    hostname_to_mac = {l.hostname.lower(): l.mac for l in leases if l.hostname and l.hostname != '*'}
    for entry in static_entries:
        if not entry.mac and entry.hostname:
            resolved = hostname_to_mac.get(entry.hostname.lower())
            if resolved:
                entry.mac = resolved
                entry.mac_from_lease = True
            else:
                entry.mac_from_lease = False
        else:
            entry.mac_from_lease = False
    grouped_dhcp_static = group_static_entries(static_entries)
    return {
        'title': 'AmneziaWG',
        'status': get_awg_status(),
        'awg_show': get_awg_show(),
        'lists': {name: read_awg_list(name) for name in list_meta if name != 'vpn_device_macs'},
        'list_meta': list_meta,
        'lan_devices': get_lan_devices(),
        'diagnostics': get_diagnostics(),
        'check_target': target,
        'check_result': check_result,
        'active_tab': 'amnezia',
        'msg': msg,
        'error': error,
        'vpn_macs_selected': vpn_macs_selected,
        'grouped_dhcp_static': grouped_dhcp_static,
    }


@app.get('/amnezia')
def amnezia_view(request: Request, target: str = '', msg: str = '', error: str = ''):
    """Вкладка AmneziaWG: статус, списки, маршрутизация."""
    return templates.TemplateResponse(
        request=request,
        name='amnezia.html',
        context=_amnezia_context(request, target=target, msg=msg, error=error),
    )


@app.post('/amnezia/service/{action}')
def amnezia_service_action(action: str):
    """Выполняет действие с AWG-сервисом: start / stop / restart / apply."""
    run_awg_action(action)
    return RedirectResponse(url='/amnezia', status_code=303)


@app.post('/amnezia/lists/{name}')
def amnezia_list_save(name: str, content: str = Form(default='')):
    """Сохраняет содержимое одного AWG-списка."""
    try:
        write_awg_list(name, content)
    except ValueError:
        raise HTTPException(status_code=404, detail='Unknown list')
    return RedirectResponse(url='/amnezia', status_code=303)


@app.post('/amnezia/lists-create')
def amnezia_list_create(
    request: Request,
    key: str = Form(default=''),
    title: str = Form(default=''),
    hint: str = Form(default=''),
):
    """Создаёт новый AWG-список (название, ключ, подсказка)."""
    ok, err = create_list(key, title, hint)
    if not ok:
        return templates.TemplateResponse(
            request=request,
            name='amnezia.html',
            context=_amnezia_context(request, error=err),
        )
    return RedirectResponse(url='/amnezia?msg=list_created', status_code=303)


@app.post('/amnezia/lists-delete/{key}')
def amnezia_list_delete(request: Request, key: str):
    """Удаляет AWG-список, переименовывает файл в .txt.deleted."""
    ok, err = delete_list(key)
    if not ok:
        return templates.TemplateResponse(
            request=request,
            name='amnezia.html',
            context=_amnezia_context(request, error=err),
        )
    return RedirectResponse(url='/amnezia?msg=list_deleted', status_code=303)


@app.post('/amnezia/lists-meta/{key}')
def amnezia_list_meta_save(
    request: Request,
    key: str,
    title: str = Form(default=''),
    hint: str = Form(default=''),
    new_key: str = Form(default=''),
):
    """Сохраняет метаданные списка: название, подсказку, ключ."""
    ok, err = update_list_meta(key, title, hint, new_key)
    if not ok:
        return templates.TemplateResponse(
            request=request,
            name='amnezia.html',
            context=_amnezia_context(request, error=err),
        )
    return RedirectResponse(url='/amnezia?msg=meta_saved', status_code=303)


@app.post('/amnezia/vpn-macs/save')
def amnezia_vpn_macs_save(request: Request, macs: list[str] = Form(default=[])):
    """Сохраняет выбранные MAC-адреса устройств для VPN-маршрутизации."""
    content = '\n'.join(sorted(macs)) + '\n' if macs else ''
    try:
        write_awg_list('vpn_device_macs', content)
    except ValueError:
        pass
    return RedirectResponse(url='/amnezia?msg=vpn_macs_saved', status_code=303)


@app.post('/amnezia/devices/add-mac')
def amnezia_add_mac(mac: str = Form(default='')):
    """Добавляет MAC-адрес в vpn_device_macs из LAN-списка."""
    add_mac_to_vpn(mac)
    return RedirectResponse(url='/amnezia', status_code=303)


@app.post('/services/{name}/restart')
def service_restart(name: str):
    """Перезапускает systemd-сервис по ключу из config.yaml."""
    config = load_config()

    try:
        result = restart_service(config, name)
    except ValueError:
        raise HTTPException(status_code=404, detail='Service not found')

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr.strip() or result.stdout.strip() or 'Restart failed',
        )

    return RedirectResponse(url='/', status_code=303)


@app.post('/backup/run')
def backup_run():
    """Запускает бэкап через home-router-backup, стримит на Mac."""
    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '-n', '/usr/local/sbin/home-router-backup'],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail='Backup timed out after 10 minutes')
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr.strip() or 'Backup failed',
        )
    return RedirectResponse(url='/?backup=ok', status_code=303)


@app.get('/capture')
def capture_traffic(request: Request, mac: str = '', seconds: int = 15, count: int = 200):
    """Перехват трафика tcpdump по MAC-адресу на интерфейсе enp2s0."""
    mac = mac.strip().lower()
    output = ''
    error = ''

    if mac:
        import re
        if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
            error = f'Некорректный MAC-адрес: {mac}'
        else:
            try:
                result = subprocess.run(
                    [
                        '/usr/bin/sudo', '-n', '/usr/bin/tcpdump',
                        '-i', 'enp2s0',
                        '-n', '-q',
                        '-c', str(min(count, 500)),
                        'ether', 'host', mac,
                    ],
                    capture_output=True, text=True,
                    timeout=min(seconds, 120) + 5,
                )
                output = result.stdout + result.stderr
            except subprocess.TimeoutExpired as e:
                stdout = e.stdout or ''
                stderr = e.stderr or ''
                if isinstance(stdout, bytes):
                    stdout = stdout.decode('utf-8', errors='replace')
                if isinstance(stderr, bytes):
                    stderr = stderr.decode('utf-8', errors='replace')
                output = stdout + stderr + f'\n--- захват остановлен после {seconds}с ---'
            except Exception as e:
                error = str(e)

    return templates.TemplateResponse(
        request=request,
        name='capture.html',
        context={
            'title': 'Перехват трафика',
            'mac': mac,
            'seconds': seconds,
            'count': count,
            'output': output,
            'error': error,
            'active_tab': 'amnezia',
        },
    )


def _build_dnsmasq_context(**extra) -> dict:
    """Собирает контекст шаблона dnsmasq.html: резервации, аренды, онлайн-статусы через ARP."""
    static = read_static()
    system = read_system_static()
    leases = read_leases()
    static_macs = {e.mac for e in static if e.mac}
    static_hosts = {e.hostname for e in static if not e.mac and e.hostname}
    system_macs = {e['mac'] for e in system}
    dynamic_lease_count = sum(
        1 for l in leases
        if l.mac not in static_macs
        and l.mac not in system_macs
        and not (l.hostname and l.hostname in static_hosts)
    )
    arp_macs, arp_ips = get_arp_online()
    if arp_macs or arp_ips:
        online_macs = arp_macs
        hostname_ip = {e.hostname.lower(): e.ip for e in static if not e.mac and e.hostname}
        online_hostnames = {hn for hn, ip in hostname_ip.items() if ip in arp_ips}
    else:
        online_macs = {l.mac for l in leases if l.mac and l.ts > 0}
        online_hostnames = {l.hostname.lower() for l in leases if l.hostname and l.hostname != '*' and l.ts > 0}
    return {
        'title': 'dnsmasq',
        'active_tab': 'dnsmasq',
        'state': get_dnsmasq_state(),
        'leases': leases,
        'static_entries': static,
        'system_static': system,
        'static_file': str(__import__('app.dnsmasq', fromlist=['STATIC_FILE']).STATIC_FILE),
        'grouped_entries': group_static_entries(static),
        'dynamic_lease_count': dynamic_lease_count,
        'online_macs': online_macs,
        'online_hostnames': online_hostnames,
        **extra,
    }


@app.get('/dnsmasq')
def dnsmasq_view(request: Request, msg: str = '', edit: str = '', edit_host: str = '', pin: str = ''):
    """Вкладка dnsmasq: резервации, аренды, онлайн-статусы устройств."""
    return templates.TemplateResponse(
        request=request,
        name='dnsmasq.html',
        context=_build_dnsmasq_context(
            msg=msg,
            edit_mac=edit.strip().lower(),
            edit_host=edit_host.strip(),
            pin_mac=pin.strip().lower(),
        ),
    )


def _dnsmasq_response(request: Request, error: str = '', msg: str = '', edit_mac: str = '', edit_host: str = '', pin_mac: str = ''):
    """Рендерит dnsmasq.html с текущим контекстом и дополнительными параметрами."""
    return templates.TemplateResponse(
        request=request,
        name='dnsmasq.html',
        context=_build_dnsmasq_context(
            msg=msg,
            error=error,
            edit_mac=edit_mac,
            edit_host=edit_host,
            pin_mac=pin_mac,
        ),
    )


@app.post('/dnsmasq/static/add')
def dnsmasq_static_add(
    request: Request,
    mac: str = Form(default=''),
    ip: str = Form(default=''),
    hostname: str = Form(default=''),
):
    """Добавляет статическую DHCP-резервацию."""
    ok, err = add_static(mac, ip, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err)
    return RedirectResponse(url='/dnsmasq?msg=saved', status_code=303)


@app.post('/dnsmasq/static/update')
def dnsmasq_static_update(
    request: Request,
    mac: str = Form(default=''),
    ip: str = Form(default=''),
    hostname: str = Form(default=''),
):
    """Обновляет существующую DHCP-резервацию."""
    ok, err = add_static(mac, ip, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err, edit_mac=mac.strip().lower())
    return RedirectResponse(url='/dnsmasq?msg=saved', status_code=303)


@app.post('/dnsmasq/static/remove')
def dnsmasq_static_remove(request: Request, mac: str = Form(default=''), hostname: str = Form(default='')):
    """Удаляет статическую DHCP-резервацию по MAC или имени."""
    ok, err = remove_static(mac, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err)
    return RedirectResponse(url='/dnsmasq?msg=removed', status_code=303)


@app.post('/dnsmasq/service/reload')
def dnsmasq_service_reload():
    """AJAX: перезагружает dnsmasq (SIGHUP). Возвращает JSON {ok, error?}."""
    ok, msg = reload_dnsmasq()
    if ok:
        return {'ok': True}
    return {'ok': False, 'error': msg or 'Не удалось перезагрузить dnsmasq'}


@app.post('/dnsmasq/service/restart')
def dnsmasq_service_restart():
    """AJAX: полный перезапуск dnsmasq. Возвращает JSON {ok, error?}."""
    ok, msg = restart_dnsmasq()
    if ok:
        return {'ok': True}
    return {'ok': False, 'error': msg or 'Не удалось перезапустить dnsmasq'}


@app.get('/dnsmasq/events')
async def dnsmasq_events():
    """SSE-поток онлайн-статусов: обновляется при изменении ARP или leases."""
    async def _generate():
        """Генератор SSE-событий: следит за ARP и leases, шлёт обновления при изменениях."""
        def _read_online():
            """Читает ARP-таблицу и возвращает (sorted_macs, sorted_hostnames)."""
            static = read_static()
            arp_macs, arp_ips = get_arp_online()
            if arp_macs or arp_ips:
                macs = sorted(arp_macs)
                hostname_ip = {e.hostname.lower(): e.ip for e in static if not e.mac and e.hostname}
                hosts = sorted(hn for hn, ip in hostname_ip.items() if ip in arp_ips)
            else:
                leases = read_leases()
                macs = sorted(l.mac for l in leases if l.mac and l.ts > 0)
                hosts = sorted(l.hostname.lower() for l in leases if l.hostname and l.hostname != '*' and l.ts > 0)
            return macs, hosts

        macs, hosts = _read_online()
        last_key = (macs, hosts)
        yield f"data: {_json.dumps({'macs': macs, 'hostnames': hosts})}\n\n"

        last_mtime: float = 0.0
        try:
            last_mtime = LEASES_FILE.stat().st_mtime
        except OSError:
            pass

        ticks = 0
        while True:
            await asyncio.sleep(2)
            ticks += 1

            try:
                mtime = LEASES_FILE.stat().st_mtime
            except OSError:
                mtime = 0.0
            leases_changed = mtime != last_mtime
            if leases_changed:
                last_mtime = mtime

            # Check ARP every 5 ticks (10 seconds)
            arp_tick = ticks % 5 == 0

            if leases_changed or arp_tick:
                macs, hosts = _read_online()
                key = (macs, hosts)
                if key != last_key:
                    last_key = key
                    yield f"data: {_json.dumps({'macs': macs, 'hostnames': hosts})}\n\n"

            if ticks % 15 == 0:
                yield ': heartbeat\n\n'

    return StreamingResponse(
        _generate(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.get('/health')
def health():
    """Проверка доступности приложения."""
    return {'status': 'ok'}
