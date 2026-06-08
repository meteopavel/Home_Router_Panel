# 🏠 Home Router Panel

Веб-панель для домашнего роутера / небольшого сервера.

Управление системными сервисами, VPN-маршрутизацией и hotlist-файлами через браузер.

---

## ✅ Что реализовано

- FastAPI + uvicorn + nginx + systemd — полный production-стек
- SVG-иконка вкладки браузера
- Три вкладки: **Обзор**, **zapret**, **AmneziaWG**

**Вкладка Обзор** — карточки состояния, статусы сервисов, кнопки перезапуска

**Вкладка zapret** — список hotlist-файлов, кнопка перезапуска, переход в редактор

**Редактор hotlist** — textarea с сохранением + автоперезапуск zapret

**Вкладка AmneziaWG**:
- Статус сервиса `awg-quick@awg0`, интерфейс, ip rule, ip_forward
- `awg show awg0` (приватные ключи никогда не показываются)
- Кнопки: Перезапустить / Запустить / Остановить / Применить маршрутизацию
- Редакторы четырёх файлов конфигурации маршрутизации
- Таблица LAN-устройств с кнопкой «+ VPN» (добавить MAC в список)
- Проверка маршрута для домена или IP
- Диагностика: ip rule, ip route table 100, iptables mangle

---

## 🛠️ Стек

- Python 3.12 · FastAPI · uvicorn · Jinja2
- nginx · systemd · sudoers
- Debian/Ubuntu

---

## 📍 Расположение на сервере

| Что | Путь |
|-----|------|
| Код | `/opt/Home_Router_Panel` |
| Venv | `/opt/Home_Router_Panel/.venv` |
| Конфиг AWG | `/etc/home-router-panel/awg/` |
| Helper-скрипт | `/usr/local/sbin/home-router-awg-config` |
| Routing up | `/usr/local/sbin/tg-vpn-routing-up.sh` |
| Routing down | `/usr/local/sbin/tg-vpn-routing-down.sh` |
| sudoers панели | `/etc/sudoers.d/home-router-panel` |

---

## 🗂️ Структура проекта

```
Home_Router_Panel/
├── app/
│   ├── amnezia.py        — AWG: статус, управление, списки, LAN, check-route
│   ├── config.py         — загрузка .env и config.yaml
│   ├── hotlists.py       — чтение/запись hotlist-файлов
│   ├── main.py           — все маршруты FastAPI
│   └── services.py       — управление systemd (subprocess + sudo)
├── scripts/
│   ├── home-router-awg-config    — helper-скрипт AWG (устанавливается вручную)
│   ├── tg-vpn-routing-up.sh      — применение маршрутизации через AWG
│   └── tg-vpn-routing-down.sh    — откат маршрутизации
├── static/
│   ├── style.css         — точка входа (@import)
│   ├── variables.css     — все CSS-переменные
│   ├── base.css          — сброс и типографика
│   ├── layout.css        — структура страницы, tabs, media queries
│   ├── components.css    — карточки, строки, пилюли, editor, code-block
│   ├── buttons.css       — кнопки
│   └── favicon.svg       — иконка вкладки
├── templates/
│   ├── base.html         — HTML-каркас, навигация (три вкладки)
│   ├── index.html        — вкладка Обзор
│   ├── zapret.html       — вкладка zapret
│   ├── hotlist_edit.html — редактор hotlist-файла
│   └── amnezia.html      — вкладка AmneziaWG
├── .env                  — секреты (не коммитится)
├── .env.example
├── config.yaml           — сервисы, hotlists, параметры панели
├── config.example.yaml
├── deploy-local.sh       — деплой: commit + push + рестарт на сервере
└── requirements.txt
```

---

## 📄 Backend — `app/`

**`main.py`** — все маршруты:

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Обзор |
| GET | `/zapret` | Вкладка zapret |
| GET | `/hotlists/{name}/edit` | Редактор hotlist |
| POST | `/hotlists/{name}/edit` | Сохранить + перезапустить zapret |
| GET | `/amnezia` | Вкладка AmneziaWG |
| POST | `/amnezia/service/{action}` | start / stop / restart / apply |
| POST | `/amnezia/lists/{name}` | Сохранить список |
| POST | `/amnezia/devices/add-mac` | Добавить MAC в vpn_device_macs |
| POST | `/services/{name}/restart` | Перезапуск сервиса (Обзор) |

**`amnezia.py`** — всё для AWG-вкладки: вызов helper-скрипта, чтение/запись файлов конфигурации, парсинг ip neigh, валидация MAC и доменов.

**`services.py`** — `get_services_status`, `restart_service` через `/usr/bin/sudo -n /usr/bin/systemctl`.

**`hotlists.py`** — `read_hotlist`, `write_hotlist`, `get_hotlists_config`.

**`config.py`** — `load_config()` читает `.env` + `config.yaml`.

---

## 🔒 Безопасность — sudoers

Панель не имеет широкого sudo. Два отдельных правила:

**1. Перезапуск сервисов (панель читает это напрямую):**
```
meteopavel ALL=(root) NOPASSWD: /usr/bin/systemctl restart zapret
meteopavel ALL=(root) NOPASSWD: /usr/bin/systemctl restart awg-quick@awg0
```

**2. AWG helper-скрипт:**
```
meteopavel ALL=(root) NOPASSWD: /usr/local/sbin/home-router-awg-config
```

Файл sudoers: `/etc/sudoers.d/home-router-panel`

---

## 🖥️ Вкладка AmneziaWG — установка на сервере

Вкладка работает без ошибок сразу после деплоя (показывает «helper недоступен»).
Для полной работы нужно выполнить один раз на сервере:

**1. Директория конфигурации:**
```bash
sudo mkdir -p /etc/home-router-panel/awg
sudo chown meteopavel: /etc/home-router-panel/awg
touch /etc/home-router-panel/awg/tg_nets.txt
touch /etc/home-router-panel/awg/figma_domains.txt
touch /etc/home-router-panel/awg/claude_domains.txt
touch /etc/home-router-panel/awg/vpn_device_macs.txt
```

**2. Helper-скрипт:**
```bash
sudo cp /opt/Home_Router_Panel/scripts/home-router-awg-config /usr/local/sbin/
sudo chmod 755 /usr/local/sbin/home-router-awg-config
sudo chown root:root /usr/local/sbin/home-router-awg-config
```

**3. Строка в sudoers** (`sudo visudo -f /etc/sudoers.d/home-router-panel`):
```
meteopavel ALL=(root) NOPASSWD: /usr/local/sbin/home-router-awg-config
```

**4. Routing-скрипты** (проверить содержимое перед установкой!):
```bash
sudo cp /opt/Home_Router_Panel/scripts/tg-vpn-routing-up.sh /usr/local/sbin/
sudo cp /opt/Home_Router_Panel/scripts/tg-vpn-routing-down.sh /usr/local/sbin/
sudo chmod 755 /usr/local/sbin/tg-vpn-routing-*.sh
sudo chown root:root /usr/local/sbin/tg-vpn-routing-*.sh
```

Скрипты читают файлы из `/etc/home-router-panel/awg/` и используют цепочку `TG_VPN_ROUTING` в iptables mangle — другие правила не затрагиваются. Идемпотентны (безопасно перезапускать).

---

## 🔀 Архитектура маршрутизации AWG

```
Пакет с LAN (enp2s0), dst != 192.168.100.0/24
    → iptables mangle PREROUTING
    → jump TG_VPN_ROUTING
    → MARK 0x66/0xff (если dst ∈ tg_nets / figma_nets / claude_nets, или src MAC в списке)
    → ip rule: fwmark 0x66/0xff → table 100
    → table 100: default dev awg0
    → трафик уходит через VPN
```

---

## 🚀 Деплой

```bash
./deploy-local.sh -q "Commit message"
```

Флаг `-q` обязателен. Без него — полный лог в контекст, захламляет сессию.
На успехе показывает только `Active:` и `✅`. На ошибке — полный вывод.

---

## 📋 Полезные команды на сервере

```bash
# Панель
systemctl status home-router-panel.service
sudo journalctl -u home-router-panel.service -f

# nginx
systemctl status nginx

# zapret
sudo journalctl -u zapret.service -f

# AWG
sudo journalctl -u awg-quick@awg0.service -f
sudo awg show awg0

# Маршрутизация
ip rule show
ip route show table 100
sudo iptables -t mangle -nvL TG_VPN_ROUTING
sudo ipset list tg_nets | head -20
```
