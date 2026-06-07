from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config


app = FastAPI(title="Home Router Panel")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


@app.get("/")
def index(request: Request):
    config = load_config()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": config.get("app", {}).get("title", "Home Router Panel"),
            "config": config,
        },
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
    }
