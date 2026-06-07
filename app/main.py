from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config
from app.hotlists import get_hotlists_config, read_hotlist
from app.services import get_services_status


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
    hotlists = get_hotlists_config(config)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": config.get("app", {}).get("title", "Home Router Panel"),
            "config": config,
            "services": services,
            "hotlists": hotlists,
        },
    )


@app.get("/hotlists/{name}")
def hotlist_view(request: Request, name: str):
    config = load_config()
    hotlist = read_hotlist(config, name)

    if hotlist is None:
        raise HTTPException(status_code=404, detail="Hotlist not found")

    return templates.TemplateResponse(
        request=request,
        name="hotlist.html",
        context={
            "title": f"Hotlist: {hotlist.name}",
            "hotlist": hotlist,
        },
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
    }