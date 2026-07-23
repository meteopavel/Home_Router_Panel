"""Вкладка Claude → GLM: перехват api.anthropic.com для выбранных MAC.

Перехват на сетевом уровне (dnsmasq ipset + iptables DNAT per-MAC — см.
scripts/home-router-claude-gateway). Этот модуль:
  - управляет списком MAC (/etc/home-router-panel/claude/macs.txt) из UI;
  - per-model роутинг POST /v1/messages*:
      Fable/Haiku → GLM (z.ai), Sonnet/Opus/прочее → настоящий Anthropic (passthrough).
    Выбором модели в приложении выбирается бэкенд (GLM без лимитов vs. настоящий Anthropic).

Остальные пути api.anthropic.com (auth/OAuth/телеметрия) nginx отдаёт настоящему
Anthropic сам (location / → proxy_pass). В Python catch-all не нужен.
"""

import json
import subprocess
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.dnsmasq import get_arp_online, group_static_entries, read_leases, read_static

CONF_DIR = Path('/etc/home-router-panel/claude')
MACS_FILE = CONF_DIR / 'macs.txt'
ZAI_KEY_FILE = CONF_DIR / 'zai.key'
HELPER = '/usr/local/sbin/home-router-claude-gateway'

ZAI_BASE = 'https://api.z.ai/api/anthropic'        # GLM
ANTHROPIC_BASE = 'https://api.anthropic.com'        # настоящий Anthropic (passthrough)
ANTHROPIC_VERSION_DEFAULT = '2023-06-01'

# Per-model роутинг: подстрока в запрошенной модели → (backend, target_model).
#   backend='zai'       → GLM через z.ai (zai_key), model заменяется на target.
#   backend='anthropic' → настоящий Anthropic (passthrough, оригинальный auth);
#                         target=None = без переименования.
ROUTING: tuple[tuple[str, str, str | None], ...] = (
    # порядок важен: более частные префиксы проверяются раньше. Fable в пикере приложения не выбирается.
    ('haiku',    'zai',       'glm-5.2'),     # Haiku → GLM 5.2 (главный GLM-слот)
    ('sonnet-4', 'zai',       'glm-4.7'),     # Sonnet 4.x (legacy в пикере) → GLM 4.7 (парковка)
    ('sonnet',   'anthropic', None),          # Sonnet 5 → настоящий Anthropic
    ('opus',     'anthropic', None),          # Opus → настоящий Anthropic
)
DEFAULT_BACKEND = 'anthropic'  # всё прочее → настоящий Anthropic (безопасный фоллбэк)

# Hop-by-hop / служебные заголовки, которые не прокидываются при passthrough.
_HOP_BY_HOP = frozenset({
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host', 'content-length',
})

PROJECT_ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=PROJECT_ROOT / 'templates')

router = APIRouter()


# ── Список MAC и helper ────────────────────────────────────────────────────────

def read_macs() -> list[str]:
    """Список MAC-адресов, для которых api.anthropic.com перехватывается."""
    if not MACS_FILE.exists():
        return []
    return [l.strip().lower() for l in MACS_FILE.read_text(encoding='utf-8').splitlines()
            if l.strip() and not l.strip().startswith('#')]


def write_macs(macs: list[str]) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    MACS_FILE.write_text('\n'.join(sorted(macs)) + '\n', encoding='utf-8')


def helper_available() -> bool:
    return Path(HELPER).exists()


def apply_redirect() -> tuple[bool, str]:
    """Перестраивает ipset + mangle-exempt + DNAT через sudo-helper."""
    try:
        r = subprocess.run(
            ['/usr/bin/sudo', '-n', HELPER, 'apply'],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, 'Timeout'
    except Exception as e:
        return False, str(e)


def get_status() -> dict:
    return {
        'helper_available': helper_available(),
        'has_zai_key': ZAI_KEY_FILE.exists(),
        'macs_count': len(read_macs()),
    }


# ── Per-model прокси /v1/messages* ─────────────────────────────────────────────

def _route(model: str) -> tuple[str, str | None]:
    """Возвращает (backend, target) по префиксу модели. backend: 'zai' | 'anthropic'."""
    m = (model or '').lower()
    for prefix, backend, target in ROUTING:
        if prefix in m:
            return backend, target
    return DEFAULT_BACKEND, None


def _read_zai_key() -> str | None:
    try:
        return ZAI_KEY_FILE.read_text(encoding='utf-8').strip() or None
    except Exception:
        return None


async def _proxy(request: Request) -> StreamingResponse:
    """POST /v1/messages* → per-model роутинг: GLM (z.ai) или настоящий Anthropic."""
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail='invalid JSON body')
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='expected JSON object')

    backend, target = _route(payload.get('model', ''))

    if backend == 'zai':
        key = _read_zai_key()
        if not key:
            raise HTTPException(status_code=503, detail=f'z.ai key missing: {ZAI_KEY_FILE}')
        upstream_url = ZAI_BASE + request.url.path
        payload['model'] = target
        fwd_headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {key}',
            'anthropic-version': request.headers.get('anthropic-version', ANTHROPIC_VERSION_DEFAULT),
            # z.ai не жмёт → отдаём клиенту как есть, без возни с Content-Encoding
            'accept-encoding': 'identity',
        }
        if request.headers.get('anthropic-beta'):
            fwd_headers['anthropic-beta'] = request.headers['anthropic-beta']
    else:  # anthropic passthrough — оригинальный auth, расходует квоту Anthropic
        upstream_url = ANTHROPIC_BASE + request.url.path
        if target is not None:
            payload['model'] = target
        # Прозрачно прокидываем ВСЕ заголовки приложения (auth, anthropic-client-*,
        # anthropic-beta, user-agent и т.д.) — иначе Anthropic режет 403.
        fwd_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() != 'accept-encoding'
        }
        fwd_headers['accept-encoding'] = 'identity'  # не жмём → отдаём клиенту как есть

    timeout = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)
    client = httpx.AsyncClient(timeout=timeout)
    try:
        req = client.build_request(
            'POST', upstream_url,
            content=json.dumps(payload).encode('utf-8'),
            headers=fwd_headers,
        )
        upstream = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f'{backend} upstream error: {e}')

    content_type = upstream.headers.get('content-type', 'application/json')

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                if chunk:
                    yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Контекст вкладки и роуты ───────────────────────────────────────────────────

def _context(request: Request, msg: str = '', error: str = '') -> dict:
    static = read_static()
    leases = read_leases()
    arp_macs, arp_ips = get_arp_online()
    hostname_to_mac = {l.hostname.lower(): l.mac for l in leases
                       if l.hostname and l.hostname != '*' and l.mac}
    for e in static:
        if not e.mac and e.hostname:
            e.mac = hostname_to_mac.get(e.hostname.lower(), '')
    status = get_status()
    return {
        'request': request,
        'active_tab': 'claude',
        'title': 'Claude → GLM',
        'grouped_static': group_static_entries(static),
        'online_macs': arp_macs,
        'online_ips': arp_ips,
        'macs': set(read_macs()),
        'helper_available': status['helper_available'],
        'has_zai_key': status['has_zai_key'],
        'msg': msg,
        'error': error,
    }


@router.get('/claude')
def claude_view(request: Request, msg: str = '', error: str = ''):
    return templates.TemplateResponse(
        request=request, name='claude.html',
        context=_context(request, msg=msg, error=error),
    )


@router.post('/claude/macs/save')
def claude_macs_save(request: Request, macs: list[str] = Form(default=[])):
    cleaned = sorted({m.strip().lower() for m in macs if m.strip()})
    write_macs(cleaned)
    return RedirectResponse(url='/claude?msg=saved', status_code=303)


@router.post('/claude/macs/save-apply')
def claude_macs_save_apply(request: Request, macs: list[str] = Form(default=[])):
    cleaned = sorted({m.strip().lower() for m in macs if m.strip()})
    write_macs(cleaned)
    if not helper_available():
        return templates.TemplateResponse(
            request=request, name='claude.html',
            context=_context(request, error='helper недоступен'),
        )
    ok, err = apply_redirect()
    if not ok:
        return templates.TemplateResponse(
            request=request, name='claude.html',
            context=_context(request, error=err),
        )
    return RedirectResponse(url='/claude?msg=applied', status_code=303)


@router.post('/v1/messages')
async def claude_messages(request: Request):
    """Anthropic Messages API → per-model роутинг (GLM или настоящий Anthropic)."""
    return await _proxy(request)


@router.post('/v1/messages/count_tokens')
async def claude_count_tokens(request: Request):
    return await _proxy(request)
