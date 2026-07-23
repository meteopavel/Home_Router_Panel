"""Вкладка Claude → GLM: редирект api.anthropic.com на GLM (z.ai) для выбранных MAC.

Перехват происходит на сетевом уровне (dnsmasq ipset + iptables DNAT per-MAC —
см. scripts/home-router-claude-gateway). Этот модуль отвечает за:
  - управление списком MAC (/etc/home-router-panel/claude/macs.txt) из UI;
  - прокси POST /v1/messages → https://api.z.ai/api/anthropic/v1/messages
    с маппингом модели (haiku→glm-4.7, sonnet/opus→glm-5.2) и z.ai-ключом.

Остальные пути api.anthropic.com (auth/OAuth/телеметрия) nginx отдаёт настоящему
Anthropic сам (location / → proxy_pass https://api.anthropic.com) — в Python catch-all
не нужен, поэтому с UI-роутами панели конфликтов нет.
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

# z.ai отдаёт нативный Anthropic Messages API; путь берём из запроса
# (/v1/messages или /v1/messages/count_tokens).
ZAI_BASE = 'https://api.z.ai/api/anthropic'
ANTHROPIC_VERSION_DEFAULT = '2023-06-01'

# Маппинг моделей: подстрока в имени claude-* → модель z.ai.
DEFAULT_GLM_MODEL = 'glm-5.2'
MODEL_PREFIX_MAP: tuple[tuple[str, str], ...] = (
    ('haiku', 'glm-4.7'),
    ('sonnet', 'glm-5.2'),
    ('opus', 'glm-5.2'),
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=PROJECT_ROOT / 'templates')

router = APIRouter()


# ── Список MAC и helper ────────────────────────────────────────────────────────

def read_macs() -> list[str]:
    """Список MAC-адресов, для которых api.anthropic.com уходит в GLM."""
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


# ── Прокси /v1/messages → GLM ──────────────────────────────────────────────────

def _map_model(model: str) -> str:
    m = (model or '').lower()
    for prefix, glm in MODEL_PREFIX_MAP:
        if prefix in m:
            return glm
    return DEFAULT_GLM_MODEL


def _read_zai_key() -> str | None:
    try:
        return ZAI_KEY_FILE.read_text(encoding='utf-8').strip() or None
    except Exception:
        return None


async def _forward_to_zai(request: Request) -> StreamingResponse:
    """POST /v1/messages* → z.ai: маппинг модели, z.ai-ключ, стриминг ответа."""
    key = _read_zai_key()
    if not key:
        raise HTTPException(status_code=503, detail=f'z.ai key missing: {ZAI_KEY_FILE}')

    raw = await request.body()
    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail='invalid JSON body')
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='expected JSON object')

    payload['model'] = _map_model(payload.get('model', ''))

    # Оставляем anthropic-*, подменяем auth на z.ai-ключ, host выставит httpx.
    fwd_headers = {
        'content-type': 'application/json',
        'authorization': f'Bearer {key}',
        'anthropic-version': request.headers.get('anthropic-version', ANTHROPIC_VERSION_DEFAULT),
    }
    if request.headers.get('anthropic-beta'):
        fwd_headers['anthropic-beta'] = request.headers['anthropic-beta']

    upstream_url = ZAI_BASE + request.url.path
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
        raise HTTPException(status_code=502, detail=f'z.ai connect error: {e}')

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
    """Anthropic Messages API → GLM (z.ai)."""
    return await _forward_to_zai(request)


@router.post('/v1/messages/count_tokens')
async def claude_count_tokens(request: Request):
    """Счётчик токенов — тоже через GLM."""
    return await _forward_to_zai(request)
