# 🏠 Home Router Panel

Веб-панель для домашнего роутера или небольшого домашнего сервера.

Предназначена для управления системными сервисами через веб-интерфейс:

- просмотр статусов сервисов;
- перезапуск выбранных systemd unit;
- управление `zapret`;
- управление `AmneziaWG` / `AWG` / `WireGuard`;
- отображение hotlist-страниц;
- дальнейшее расширение функций.

---

## ✅ Текущее состояние

Реализовано:

- FastAPI-приложение панели;
- запуск панели через `systemd`;
- `nginx` как reverse proxy перед `uvicorn`;
- HTML-шаблоны через `templates`;
- статические стили через `static/` (разбиты по файлам);
- конфигурация через `.env` и `config.yaml`;
- отображение главной страницы панели;
- отображение страницы hotlists;
- отображение статусов сервисов;
- кнопки перезапуска системных сервисов;
- рестарт `zapret` через кнопку на морде;
- рестарт `AWG/WireGuard` unit через кнопку на морде;
- безопасный вызов `systemctl` через ограниченный `sudoers`;
- SVG-иконка вкладки браузера.

Кнопки рестарта на веб-морде проверены и работают.

---

## 🛠️ Стек

- Python 3.12
- FastAPI
- uvicorn
- Jinja2 templates
- nginx
- systemd
- sudoers
- Debian/Ubuntu

---

## 📍 Расположение проекта

Код: `/opt/Home_Router_Panel`

Виртуальное окружение: `/opt/Home_Router_Panel/.venv`

---

## 🗂️ Структура проекта

```
Home_Router_Panel/
├── .venv/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── hotlists.py
│   ├── main.py
│   └── services.py
├── static/
│   ├── style.css
│   ├── variables.css
│   ├── base.css
│   ├── layout.css
│   ├── components.css
│   ├── buttons.css
│   └── favicon.svg
├── templates/
│   ├── base.html
│   ├── hotlist.html
│   └── index.html
├── .env
├── .env.example
├── .gitignore
├── config.example.yaml
├── config.yaml
├── deploy-local.sh
├── README.md
└── requirements.txt
```

---

## 📄 Назначение основных файлов

### ⚙️ Backend — `app/`

**`main.py`** — маршруты FastAPI, подключение шаблонов и static-файлов, обработчики кнопок на морде.

**`config.py`** — загрузка настроек из `.env` и `config.yaml`. Через конфигурацию задаются параметры панели и управляемые сервисы.

**`services.py`** — логика управления systemd: получение статуса, перезапуск сервисов через `subprocess`. Использует абсолютные пути `/usr/bin/sudo` и `/usr/bin/systemctl`, `sudo` с флагом `-n`.

**`hotlists.py`** — подготовка и отображение hotlist-страниц.

---

### 🖥️ Шаблоны — `templates/`

**`base.html`** — общий HTML-каркас: подключение CSS, иконки, общие элементы интерфейса.

**`index.html`** — главная страница: карточки состояния, статусы сервисов, кнопки управления.

**`hotlist.html`** — страница просмотра отдельного hotlist.

---

### 🎨 Стили — `static/`

**`style.css`** — точка входа, содержит только `@import` остальных файлов.

**`variables.css`** — все CSS-переменные (`--bg`, `--text`, `--border`, `--radius-*`, `--bg-*`, `--font-mono` и др.). Единственное место для изменения цветовой схемы.

**`base.css`** — сброс и типографика: `*`, `body`, `h1`, `h2`, `p`.

**`layout.css`** — структура страницы: `.page`, `.header`, `.grid`, `.footer`, media queries.

**`components.css`** — UI-компоненты: карточки, строки сервисов, пилюли статусов, hotlist-вью, пустое состояние.

**`buttons.css`** — стили кнопок: `.button`, состояния hover/active/disabled, `.inline-form`.

**`favicon.svg`** — иконка вкладки браузера. SVG-роутер с антеннами в цветах панели.

---

### 🔧 Конфигурация

**`.env`** — секреты и параметры конкретной установки. Не коммитится.

**`.env.example`** — шаблон для новой установки.

**`config.yaml`** — список управляемых сервисов, hotlist-файлов и параметров панели.

**`config.example.yaml`** — шаблон конфига для новой машины.

---

### 🚀 Скрипты

**`deploy-local.sh`** — деплой на сервер: git commit + push, обновление на сервере, перезапуск сервиса.

```
./deploy-local.sh -q "Commit message"
```

Флаг `-q` — тихий режим: выводит только статус сервиса и итог. Без флага — полный лог.

**`requirements.txt`** — зависимости Python для установки в виртуальное окружение.

---

## 🏗️ Архитектура работы

```
Браузер → nginx → uvicorn → FastAPI → systemd (через sudo)
```

1. Пользователь открывает веб-морду в браузере.
2. `nginx` принимает запрос и проксирует в `uvicorn`.
3. `uvicorn` обслуживает FastAPI-приложение.
4. FastAPI рендерит HTML-шаблоны из `templates`.
5. Браузер получает HTML, CSS и favicon из `static`.
6. При нажатии кнопок запрос уходит в backend.
7. Backend вызывает функции из `app/services.py`.
8. `services.py` вызывает `systemctl` через разрешённый `sudo`.
9. `systemd` выполняет действие над нужным unit.

---

## 🔀 nginx

Используется как reverse proxy: принимает HTTP от браузера и проксирует на локальный `uvicorn`. Python-логика находится в FastAPI, не в nginx.

---

## ⚙️ systemd-сервис панели

Панель работает как systemd-сервис — поднимается автоматически после перезагрузки сервера.

Логи: `sudo journalctl -u home-router-panel.service -f`

---

## 🔒 Управление сервисами и sudoers

Панель управляет только заранее разрешёнными unit. Сейчас: `zapret` и `AWG/WireGuard`.

Рестарт выполняется командой:

```
/usr/bin/sudo -n /usr/bin/systemctl restart SERVICE_UNIT
```

Sudoers-файл: `/etc/sudoers.d/home-router-panel`

Редактировать через: `sudo visudo -f /etc/sudoers.d/home-router-panel`

Разрешать только конкретные unit:

- `zapret` / `zapret.service`
- `awg-quick@awg0` / `awg-quick@awg0.service`

Пользователь в sudoers должен совпадать с пользователем systemd-сервиса панели (`systemctl cat home-router-panel.service`).

---

## 📋 Полезные команды

### Панель

```bash
systemctl status home-router-panel.service   # статус
sudo journalctl -u home-router-panel.service -f  # логи
```

### nginx

```bash
systemctl status nginx
curl -I http://127.0.0.1
```

### zapret

```bash
sudo journalctl -u zapret.service -f
systemctl show zapret.service -p ActiveEnterTimestamp
systemctl list-units --type=service | grep -Ei "zapret"
```

### AWG / WireGuard

```bash
sudo journalctl -u awg-quick@awg0.service -f
systemctl show awg-quick@awg0.service -p ActiveEnterTimestamp
systemctl list-units --type=service | grep -Ei "awg|amnezia|wg|wireguard"
```

---

## 📏 Правила разработки

- Основная логика FastAPI — `app/main.py`.
- Работа с конфигурацией — `app/config.py`.
- Работа с сервисами — `app/services.py`.
- Логика hotlists — `app/hotlists.py`.
- HTML-шаблоны — `templates/`.
- CSS разбит по файлам в `static/`; `style.css` — точка входа с `@import`.
- Для системных команд использовать абсолютные пути (`/usr/bin/sudo`, `/usr/bin/systemctl`).
- `sudo` всегда с флагом `-n`.
- Не выдавать панели полный root-доступ.
- В sudoers разрешать только конкретные команды.
- После изменения backend-кода перезапускать сервис панели.
- После изменения systemd unit выполнять `daemon-reload`.
- Ошибки backend смотреть через journal, не через nginx.
