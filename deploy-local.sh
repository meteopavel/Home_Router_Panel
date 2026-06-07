#!/usr/bin/env bash
#===============================================================================
# DEPLOY SCRIPT FOR Home_Router_Panel
#===============================================================================

set -euo pipefail

DEFAULT_COMMIT_MSG="Update project"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$PROJECT_ROOT/.env"

cd "$PROJECT_ROOT"

# Parse args: [-q|--quiet] [commit message]
QUIET=0
COMMIT_MSG=""
for arg in "$@"; do
    case "$arg" in
        -q|--quiet) QUIET=1 ;;
        *) COMMIT_MSG="$arg" ;;
    esac
done
COMMIT_MSG="${COMMIT_MSG:-$DEFAULT_COMMIT_MSG}"

log() {
    if [[ "$QUIET" -eq 0 ]]; then echo "$@"; fi
}

get_env() {
    local var_name="$1"
    local env_file="$2"

    if [[ ! -f "$env_file" ]]; then
        echo ""
        return
    fi

    grep -E "^${var_name}=" "$env_file" 2>/dev/null | head -1 | cut -d'=' -f2-
}

require_env() {
    local var_name="$1"
    local var_value="$2"

    if [[ -z "$var_value" ]]; then
        echo "❌ Ошибка: переменная $var_name не найдена или пустая в $ENV_FILE"
        exit 1
    fi
}

log "🚀 Home_Router_Panel deploy"
log "📁 Project root: $PROJECT_ROOT"
log "----------------------------------------"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Файл .env не найден: $ENV_FILE"
    echo "💡 Создай его из .env.example:"
    echo "   cp .env.example .env"
    exit 1
fi

DEPLOY_USER=$(get_env "DEPLOY_USER" "$ENV_FILE")
DEPLOY_HOST=$(get_env "DEPLOY_HOST" "$ENV_FILE")
DEPLOY_PORT=$(get_env "DEPLOY_PORT" "$ENV_FILE")
DEPLOY_APP_DIR=$(get_env "DEPLOY_APP_DIR" "$ENV_FILE")
DEPLOY_SERVICE=$(get_env "DEPLOY_SERVICE" "$ENV_FILE")
DEPLOY_BRANCH=$(get_env "DEPLOY_BRANCH" "$ENV_FILE")

require_env "DEPLOY_USER" "$DEPLOY_USER"
require_env "DEPLOY_HOST" "$DEPLOY_HOST"
require_env "DEPLOY_PORT" "$DEPLOY_PORT"
require_env "DEPLOY_APP_DIR" "$DEPLOY_APP_DIR"
require_env "DEPLOY_SERVICE" "$DEPLOY_SERVICE"
require_env "DEPLOY_BRANCH" "$DEPLOY_BRANCH"

log "🔧 Deploy config:"
log "   User:    $DEPLOY_USER"
log "   Host:    $DEPLOY_HOST"
log "   Port:    $DEPLOY_PORT"
log "   App dir: $DEPLOY_APP_DIR"
log "   Service: $DEPLOY_SERVICE"
log "   Branch:  $DEPLOY_BRANCH"
log "----------------------------------------"

log "🔐 Проверка SSH-доступа к серверу..."
ssh -p "$DEPLOY_PORT" \
    -o ConnectTimeout=5 \
    "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "echo 'SSH connection OK'" > /dev/null
log "✅ SSH-доступ к серверу есть"
log "----------------------------------------"

log "📦 Этап 1/2: commit & push"
git add .
if ! git diff --staged --quiet; then
    GIT_Q=""
    [[ "$QUIET" -eq 1 ]] && GIT_Q="-q"
    git commit $GIT_Q -m "$COMMIT_MSG"
    git push $GIT_Q origin "$DEPLOY_BRANCH"
    echo "✅ Закоммичено: $COMMIT_MSG"
else
    log "⚠️ Нет изменений для коммита"
    GIT_Q=""
    [[ "$QUIET" -eq 1 ]] && GIT_Q="-q"
    git push $GIT_Q origin "$DEPLOY_BRANCH"
fi

log "----------------------------------------"
log "🖥️ Этап 2/2: server deploy"

run_remote() {
    ssh -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail

cd "$DEPLOY_APP_DIR"
git fetch origin "$DEPLOY_BRANCH" -q
git checkout "$DEPLOY_BRANCH" -q
git pull origin "$DEPLOY_BRANCH" -q

if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q

sudo -n systemctl restart "$DEPLOY_SERVICE"
sudo -n systemctl status "$DEPLOY_SERVICE" --no-pager --lines=5
echo "✅ Server deploy completed"
EOF
}

if [[ "$QUIET" -eq 1 ]]; then
    DEPLOY_OUT=$(run_remote 2>&1) || { echo "❌ Ошибка деплоя:"; echo "$DEPLOY_OUT"; exit 1; }
    echo "$DEPLOY_OUT" | grep -E "Active:|✅ Server deploy"
else
    run_remote
fi

log "----------------------------------------"
echo "✅ Деплой завершён успешно"
