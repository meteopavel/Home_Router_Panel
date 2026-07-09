#!/usr/bin/env bash
#===============================================================================
# RESTORE DATABASES TO MAC — фоллбэк, если homerouter внезапно недоступен
#===============================================================================
# Скачивает последний ночной бэкап БД (mailganer + EDU multisite) с
# backup-сервера, поднимает локальные Docker-контейнеры и восстанавливает
# в них данные. Не трогает конфиги проектов — DB_IP/DB_HOST переключить
# на localhost нужно руками после восстановления.
#
# Использование:
#   ./scripts/restore-databases-to-mac.sh
#
# Требования:
#   - ~/.ssh/config алиас vh430.timeweb.ru (уже настроен)
#   - 7z (brew install p7zip)
#   - Пароль архива — тот же, что вписан в backup.conf на роутере
#===============================================================================

set -euo pipefail

MAILGANER_DIR="$HOME/PycharmProjects/mailganer"
EDU_DIR="$HOME/PycharmProjects/Django_EDU_Multisite"
BACKUP_HOST="vh430.timeweb.ru"
BACKUP_PATH="/home/c/cj82062/Backup/home_router_panel/db-backup/db-backup-latest.7z"

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

echo "🚀 Поднимаем контейнеры mailganer (postgres/rabbitmq/memcached)..."
(cd "$MAILGANER_DIR" && docker compose up -d)

echo "🚀 Поднимаем контейнер EDU (mysql)..."
(cd "$EDU_DIR" && docker compose up -d)

echo "⏳ Ждём готовности postgres..."
for i in $(seq 1 30); do
    docker exec mailganer-postgres-1 pg_isready -U postgres >/dev/null 2>&1 && break
    sleep 2
done

echo "⏳ Ждём готовности mysql..."
for i in $(seq 1 30); do
    docker exec edu_mysql mysqladmin ping -uroot -prootpass >/dev/null 2>&1 && break
    sleep 2
done

echo "📤 Восстанавливаем postgres (tp)..."
docker exec -i mailganer-postgres-1 psql -U postgres -d tp < "$WORKDIR/mailganer_postgres_tp.sql"

echo "📤 Восстанавливаем mysql (все базы)..."
docker exec -i edu_mysql mysql -uroot -prootpass < "$WORKDIR/edu_mysql_all.sql"

echo "----------------------------------------"
echo "✅ Данные восстановлены локально на Mac."
echo ""
echo "Осталось переключить настройки на localhost:"
echo "  mailganer: mailguner/local_settings.py → раскомментировать DB_IP = 'localhost'"
echo "  EDU:       .env → DB_HOST=127.0.0.1 (или удалить строку)"
