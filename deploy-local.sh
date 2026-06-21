#!/usr/bin/env bash
#===============================================================================
# DEPLOY SCRIPT FOR Home_Router_Panel
#===============================================================================

set -euo pipefail

DEFAULT_COMMIT_MSG="Update project"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$PROJECT_ROOT/.env"
ARCHIVE_DIR="$PROJECT_ROOT/secure"
ARCHIVE_NAME="sensitive_bundle.7z"
ARCHIVE_PATH="${ARCHIVE_DIR}/${ARCHIVE_NAME}"

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

update_project_passport() {
    log "🪪 Обновляем паспорт проекта..."
    local tools_dir
    tools_dir="$(dirname "${PROJECT_ROOT}")/meteopavel/tools"
    local python_bin="${PROJECT_ROOT}/.venv/bin/python"
    (
        cd "${PROJECT_ROOT}"
        "${python_bin}" "${tools_dir}/extract_api_map.py" app \
            --project-root . --exclude .venv __pycache__ node_modules
        "${python_bin}" "${tools_dir}/build_project_passport.py" --project-root .
    )
    log "✅ Паспорт проекта обновлён."
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

rsync_via_tunnel() {
    local user="$1" host="$2" password="$3" src="$4" dest="$5"
    shift 5
    local ctl="/tmp/ssh_ctl_${user}_${host}"
    export SSHPASS="$password"
    sshpass -e ssh -o StrictHostKeyChecking=no \
        -o ControlMaster=yes -o ControlPath="$ctl" -o ControlPersist=60s \
        -nNf "${user}@${host}"
    rsync -avz --progress "$@" \
        --rsh="ssh -o StrictHostKeyChecking=no -o ControlMaster=no -o ControlPath=$ctl" \
        "$src" "${user}@${host}:${dest}"
    ssh -o ControlPath="$ctl" -O exit "${user}@${host}" 2>/dev/null || true
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

ARCHIVE_PASSWORD=$(get_env "ARCHIVE_PASSWORD" "$ENV_FILE")
SECURE_RSYNC_USER=$(get_env "SECURE_RSYNC_USER" "$ENV_FILE")
SECURE_RSYNC_HOST=$(get_env "SECURE_RSYNC_HOST" "$ENV_FILE")
SECURE_RSYNC_PATH=$(get_env "SECURE_RSYNC_PATH" "$ENV_FILE")
SECURE_RSYNC_PASSWORD=$(get_env "SECURE_RSYNC_PASSWORD" "$ENV_FILE")

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

log "----------------------------------------"
log "🔐 Этап 1/3: backup sensitive files"

BACKUP_OK=1
if [[ -z "$ARCHIVE_PASSWORD" || -z "$SECURE_RSYNC_USER" || -z "$SECURE_RSYNC_HOST" || -z "$SECURE_RSYNC_PATH" || -z "$SECURE_RSYNC_PASSWORD" ]]; then
    echo "⚠️  Backup: переменные ARCHIVE_PASSWORD / SECURE_RSYNC_* не заданы в .env — пропускаем резервное копирование"
    BACKUP_OK=0
fi

if [[ "$BACKUP_OK" -eq 1 ]]; then
    if ! command -v 7z &> /dev/null; then
        echo "⚠️  Backup: команда 7z не найдена — пропускаем резервное копирование"
        BACKUP_OK=0
    fi
fi

if [[ "$BACKUP_OK" -eq 1 ]]; then
    mkdir -p "${ARCHIVE_DIR}"
    if [[ -f "${ARCHIVE_PATH}" ]]; then
        rm -f "${ARCHIVE_PATH}"
    fi
    log "🔒 Создаём зашифрованный архив (.env)..."
    (
        cd "${PROJECT_ROOT}"
        7z a -p"${ARCHIVE_PASSWORD}" -mhe=on "${ARCHIVE_PATH}" ".env" > /dev/null
    )
    # log "📤 Отправляем архив на backup-сервер..."
    # rsync_via_tunnel "${SECURE_RSYNC_USER}" "${SECURE_RSYNC_HOST}" "${SECURE_RSYNC_PASSWORD}" \
    #     "${ARCHIVE_PATH}" "${SECURE_RSYNC_PATH}"
    echo "⚠️  rsync временно отключён — backup-сервер недоступен"
fi

log "----------------------------------------"
update_project_passport

log "----------------------------------------"
log "📦 Этап 2/3: commit & push"
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
log "🖥️ Этап 3/3: server deploy"

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
