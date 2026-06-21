from pathlib import Path
import subprocess

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dnsmasq import (
    add_static,
    get_dnsmasq_state,
    read_leases,
    read_static,
    read_system_static,
    reload_dnsmasq,
    remove_static,
    restart_dnsmasq,
)
from app.amnezia import (
    LIST_META,
    add_mac_to_vpn,
    check_route,
    get_awg_show,
    get_awg_status,
    get_diagnostics,
    get_lan_devices,
    read_awg_list,
    run_awg_action,
    write_awg_list,
)
from app.config import load_config
from app.hotlists import get_hotlists_config, read_hotlist, write_hotlist
from app.services import get_services_status, restart_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


app = FastAPI(title="Home Router Panel")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/")
def index(request: Request):
    config = load_config()
    services = get_services_status(config)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": config.get("app", {}).get("title", "Home Router Panel"),
            "config": config,
            "services": services,
            "active_tab": "overview",
        },
    )


@app.get("/zapret")
def zapret_view(request: Request):
    config = load_config()
    hotlists = get_hotlists_config(config)
    services = get_services_status(config)
    zapret_service = next((s for s in services if s.key == "zapret"), None)

    return templates.TemplateResponse(
        request=request,
        name="zapret.html",
        context={
            "title": "zapret",
            "hotlists": hotlists,
            "zapret_service": zapret_service,
            "active_tab": "zapret",
        },
    )


@app.get("/hotlists/{name}")
def hotlist_view(name: str):
    return RedirectResponse(url=f"/hotlists/{name}/edit", status_code=302)


@app.get("/hotlists/{name}/edit")
def hotlist_edit_view(request: Request, name: str):
    config = load_config()
    hotlist = read_hotlist(config, name)

    if hotlist is None:
        raise HTTPException(status_code=404, detail="Hotlist not found")

    return templates.TemplateResponse(
        request=request,
        name="hotlist_edit.html",
        context={
            "title": f"Редактировать: {hotlist.name}",
            "hotlist": hotlist,
            "active_tab": "zapret",
        },
    )


@app.post("/hotlists/{name}/edit")
def hotlist_edit_save(request: Request, name: str, content: str = Form(default="")):
    config = load_config()

    try:
        write_hotlist(config, name, content)
    except ValueError:
        raise HTTPException(status_code=404, detail="Hotlist not found")

    restart_error = ""
    try:
        result = restart_service(config, "zapret")
        if result.returncode != 0:
            restart_error = result.stderr.strip() or result.stdout.strip() or "zapret не перезапустился"
    except Exception as e:
        restart_error = str(e)

    if restart_error:
        hotlist = read_hotlist(config, name)
        return templates.TemplateResponse(
            request=request,
            name="hotlist_edit.html",
            context={
                "title": f"Редактировать: {hotlist.name}",
                "hotlist": hotlist,
                "active_tab": "zapret",
                "restart_error": restart_error,
            },
        )

    return RedirectResponse(url=f"/hotlists/{name}/edit?saved=1", status_code=303)


@app.get("/amnezia")
def amnezia_view(request: Request, target: str = ""):
    status = get_awg_status()
    awg_show = get_awg_show()
    lists = {name: read_awg_list(name) for name in LIST_META}
    lan_devices = get_lan_devices()
    diagnostics = get_diagnostics()

    check_result = None
    if target:
        check_result = check_route(target)

    return templates.TemplateResponse(
        request=request,
        name="amnezia.html",
        context={
            "title": "AmneziaWG",
            "status": status,
            "awg_show": awg_show,
            "lists": lists,
            "list_meta": LIST_META,
            "lan_devices": lan_devices,
            "diagnostics": diagnostics,
            "check_target": target,
            "check_result": check_result,
            "active_tab": "amnezia",
        },
    )


@app.post("/amnezia/service/{action}")
def amnezia_service_action(action: str):
    run_awg_action(action)
    return RedirectResponse(url="/amnezia", status_code=303)


@app.post("/amnezia/lists/{name}")
def amnezia_list_save(name: str, content: str = Form(default="")):
    try:
        write_awg_list(name, content)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown list")
    return RedirectResponse(url="/amnezia", status_code=303)


@app.post("/amnezia/devices/add-mac")
def amnezia_add_mac(mac: str = Form(default="")):
    add_mac_to_vpn(mac)
    return RedirectResponse(url="/amnezia", status_code=303)


@app.post("/services/{name}/restart")
def service_restart(name: str):
    config = load_config()

    try:
        result = restart_service(config, name)
    except ValueError:
        raise HTTPException(status_code=404, detail="Service not found")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr.strip() or result.stdout.strip() or "Restart failed",
        )

    return RedirectResponse(url="/", status_code=303)


@app.post("/backup/run")
def backup_run():
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/local/sbin/home-router-backup"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Backup timed out after 10 minutes")
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr.strip() or "Backup failed",
        )
    return RedirectResponse(url="/?backup=ok", status_code=303)


@app.get("/capture")
def capture_traffic(request: Request, mac: str = "", seconds: int = 15, count: int = 200):
    mac = mac.strip().lower()
    output = ""
    error = ""

    if mac:
        import re
        if not re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
            error = f"Некорректный MAC-адрес: {mac}"
        else:
            try:
                result = subprocess.run(
                    [
                        "/usr/bin/sudo", "-n", "/usr/bin/tcpdump",
                        "-i", "enp2s0",
                        "-n", "-q",
                        "-c", str(min(count, 500)),
                        "ether", "host", mac,
                    ],
                    capture_output=True, text=True,
                    timeout=min(seconds, 120) + 5,
                )
                output = result.stdout + result.stderr
            except subprocess.TimeoutExpired as e:
                stdout = e.stdout or ""
                stderr = e.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                output = stdout + stderr + f"\n--- захват остановлен после {seconds}с ---"
            except Exception as e:
                error = str(e)

    return templates.TemplateResponse(
        request=request,
        name="capture.html",
        context={
            "title": "Перехват трафика",
            "mac": mac,
            "seconds": seconds,
            "count": count,
            "output": output,
            "error": error,
            "active_tab": "amnezia",
        },
    )


@app.get("/dnsmasq")
def dnsmasq_view(request: Request, msg: str = "", edit: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="dnsmasq.html",
        context={
            "title": "dnsmasq",
            "active_tab": "dnsmasq",
            "state": get_dnsmasq_state(),
            "leases": read_leases(),
            "static_entries": read_static(),
            "system_static": read_system_static(),
            "static_file": str(__import__("app.dnsmasq", fromlist=["STATIC_FILE"]).STATIC_FILE),
            "msg": msg,
            "edit_mac": edit.strip().lower(),
        },
    )


def _dnsmasq_response(request: Request, error: str = "", msg: str = "", edit_mac: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="dnsmasq.html",
        context={
            "title": "dnsmasq",
            "active_tab": "dnsmasq",
            "state": get_dnsmasq_state(),
            "leases": read_leases(),
            "static_entries": read_static(),
            "system_static": read_system_static(),
            "static_file": str(__import__("app.dnsmasq", fromlist=["STATIC_FILE"]).STATIC_FILE),
            "msg": msg,
            "error": error,
            "edit_mac": edit_mac,
        },
    )


@app.post("/dnsmasq/static/add")
def dnsmasq_static_add(
    request: Request,
    mac: str = Form(default=""),
    ip: str = Form(default=""),
    hostname: str = Form(default=""),
):
    ok, err = add_static(mac, ip, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err)
    return RedirectResponse(url="/dnsmasq?msg=saved", status_code=303)


@app.post("/dnsmasq/static/update")
def dnsmasq_static_update(
    request: Request,
    mac: str = Form(default=""),
    ip: str = Form(default=""),
    hostname: str = Form(default=""),
):
    ok, err = add_static(mac, ip, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err, edit_mac=mac.strip().lower())
    return RedirectResponse(url="/dnsmasq?msg=saved", status_code=303)


@app.post("/dnsmasq/static/remove")
def dnsmasq_static_remove(request: Request, mac: str = Form(default=""), hostname: str = Form(default="")):
    ok, err = remove_static(mac, hostname)
    if not ok:
        return _dnsmasq_response(request, error=err)
    return RedirectResponse(url="/dnsmasq?msg=removed", status_code=303)


@app.post("/dnsmasq/service/reload")
def dnsmasq_service_reload():
    reload_dnsmasq()
    return RedirectResponse(url="/dnsmasq?msg=reloaded", status_code=303)


@app.post("/dnsmasq/service/restart")
def dnsmasq_service_restart():
    restart_dnsmasq()
    return RedirectResponse(url="/dnsmasq?msg=restarted", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
