from pathlib import Path
import subprocess

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
def hotlist_edit_save(name: str, content: str = Form(default="")):
    config = load_config()

    try:
        write_hotlist(config, name, content)
    except ValueError:
        raise HTTPException(status_code=404, detail="Hotlist not found")

    try:
        restart_service(config, "zapret")
    except Exception:
        pass

    return RedirectResponse(url=f"/hotlists/{name}/edit", status_code=303)


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


@app.get("/health")
def health():
    return {"status": "ok"}
