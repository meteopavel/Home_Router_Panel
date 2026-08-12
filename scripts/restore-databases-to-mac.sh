#!/usr/bin/env bash
#===============================================================================
# RESTORE DATABASES TO MAC — фоллбэк, если homerouter внезапно недоступен
#===============================================================================
# Скачивает последний ночной бэкап БД (postgres + mysql) с backup-сервера,
# поднимает локальные Docker-контейнеры и восстанавливает в них данные.
# Не трогает конфиги проектов — переключить БД на localhost нужно руками
# после восстановления.
#
# Все проект-специфичные значения (хост бэкапа, пути, имена контейнеров,
# дамп-файлов, креды) вынесены в конфиг — скрипт универсальный.
#
# Использование:
#   ./scripts/restore-databases-to-mac.sh
#
# Требования:
#   - Конфиг $HOME/.config/home-router-panel/restore.conf
#     (см. scripts/restore.conf.example). Путь переопределяется через RESTORE_CONF.
#   - 7z (brew install p7zip)
#   - Пароль архива — тот же, что вписан в backup.conf на роутере
#===============================================================================

set -euo pipefail

CONF_FILE="${RESTORE_CONF:-$HOME/.config/home-router-panel/restore.conf}"
if [[ -f "$CONF_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONF_FILE"
fi

# Проверяем обязательные ключи конфига (после source).
: "${BACKUP_HOST:?BACKUP_HOST not set in $CONF_FILE}"
: "${BACKUP_PATH:?BACKUP_PATH not set in $CONF_FILE}"
: "${PROJECT_A_DIR:?PROJECT_A_DIR not set in $CONF_FILE}"
: "${PROJECT_A_CONTAINER:?PROJECT_A_CONTAINER not set in $CONF_FILE}"
: "${PROJECT_A_DB:?PROJECT_A_DB not set in $CONF_FILE}"
: "${PROJECT_A_DUMP:?PROJECT_A_DUMP not set in $CONF_FILE}"
: "${PROJECT_B_DIR:?PROJECT_B_DIR not set in $CONF_FILE}"
: "${PROJECT_B_CONTAINER:?PROJECT_B_CONTAINER not set in $CONF_FILE}"
: "${PROJECT_B_DUMP:?PROJECT_B_DUMP not set in $CONF_FILE}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD not set in $CONF_FILE}"

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

echo "🔑 Пароль архива бэкапа:"
read -rs ARCHIVE_PASSWORD
echo

echo "📥 Скачиваем последний бэкап с ${BACKUP_HOST}..."
scp "${BACKUP_HOST}:${BACKUP_PATH}" "$WORKDIR/db-backup.7z"

echo "🔓 Распаковываем..."
7z x -p"${ARCHIVE_PASSWORD}" -o"$WORKDIR" "$WORKDIR/db-backup.7z" > /dev/null

echo "🐳 Проверяем Docker Desktop..."
if ! docker info >/dev/null 2>&1; then
    open -a Docker
    echo "⏳ Ждём запуска Docker Desktop..."
    for i in $(seq 1 30); do
        docker info >/dev/null 2>&1 && break
        sleep 2
    done
fi

echo "🚀 Поднимаем контейнеры проекта A (postgres/rabbitmq/memcached)..."
(cd "$PROJECT_A_DIR" && docker compose up -d)

echo "🚀 Поднимаем контейнер проекта B (mysql)..."
(cd "$PROJECT_B_DIR" && docker compose up -d)

echo "⏳ Ждём готовности postgres..."
for i in $(seq 1 30); do
    docker exec "$PROJECT_A_CONTAINER" pg_isready -U postgres >/dev/null 2>&1 && break
    sleep 2
done

echo "⏳ Ждём готовности mysql..."
for i in $(seq 1 30); do
    docker exec "$PROJECT_B_CONTAINER" mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" >/dev/null 2>&1 && break
    sleep 2
done

echo "📤 Восстанавливаем postgres (${PROJECT_A_DB})..."
docker exec -i "$PROJECT_A_CONTAINER" psql -U postgres -d "$PROJECT_A_DB" < "$WORKDIR/$PROJECT_A_DUMP"

echo "📤 Восстанавливаем mysql (все базы)..."
docker exec -i "$PROJECT_B_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < "$WORKDIR/$PROJECT_B_DUMP"

echo "----------------------------------------"
echo "✅ Данные восстановлены локально на Mac."
echo ""
echo "Осталось переключить настройки на localhost:"
echo "  проект A:  переключить БД на localhost в настройках проекта"
echo "  проект B:  .env → DB_HOST=127.0.0.1 (или удалить строку)"
