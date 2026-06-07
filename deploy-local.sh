#!/usr/bin/env bash
#===============================================================================
# DEPLOY SCRIPT FOR Home_Router_Panel
#===============================================================================

set -euo pipefail

DEFAULT_COMMIT_MSG="Update project"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$PROJECT_ROOT/.env"

cd "$PROJECT_ROOT"

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

echo "🚀 Home_Router_Panel deploy"
echo "📁 Project root: $PROJECT_ROOT"
echo "----------------------------------------"

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

COMMIT_MSG="${1:-$DEFAULT_COMMIT_MSG}"

echo "🔧 Deploy config:"
echo "   User:    $DEPLOY_USER"
echo "   Host:    $DEPLOY_HOST"
echo "   Port:    $DEPLOY_PORT"
echo "   App dir: $DEPLOY_APP_DIR"
echo "   Service: $DEPLOY_SERVICE"
echo "   Branch:  $DEPLOY_BRANCH"
echo "----------------------------------------"

echo "🔐 Проверка SSH-доступа к серверу..."

ssh -p "$DEPLOY_PORT" \
    -o ConnectTimeout=5 \
    "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "echo 'SSH connection OK'"

echo "✅ SSH-доступ к серверу есть"
echo "----------------------------------------"

echo "📦 Этап 1/2: commit & push"

git add .

if ! git diff --staged --quiet; then
    git commit -m "$COMMIT_MSG"
    git push origin "$DEPLOY_BRANCH"
    echo "✅ Изменения закоммичены и отправлены"
else
    echo "⚠️ Нет изменений для коммита"
    echo "📤 Делаю git push на всякий случай..."
    git push origin "$DEPLOY_BRANCH"
fi

echo "----------------------------------------"

echo "🖥️ Этап 2/2: server deploy"

ssh -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail

echo "📁 Переход в директорию проекта"
cd "$DEPLOY_APP_DIR"

echo "🔄 Обновление репозитория"
git fetch origin "$DEPLOY_BRANCH"
git checkout "$DEPLOY_BRANCH"
git pull origin "$DEPLOY_BRANCH"

echo "🐍 Проверка virtualenv"
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi

echo "📦 Обновление зависимостей"
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "🔁 Перезапуск сервиса"
sudo systemctl restart "$DEPLOY_SERVICE"

echo "📊 Статус сервиса"
sudo systemctl status "$DEPLOY_SERVICE" --no-pager --lines=20

echo "✅ Server deploy completed"
EOF

echo "----------------------------------------"
echo "✅ Деплой завершён успешно"