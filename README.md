# Home Router Panel

[![Python](https://img.shields.io/badge/Python-3.x-3776AB)](https://docs.python.org/3/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688)](https://fastapi.tiangolo.com/release-notes/)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-4996C8)](https://www.uvicorn.org/)
[![Jinja](https://img.shields.io/badge/Jinja2-templates-B41717)](https://jinja.palletsprojects.com/)
[![Nginx](https://img.shields.io/badge/Nginx-reverse_proxy-009639)](https://nginx.org/en/docs/)

Веб-панель на FastAPI для локального управления домашним роутером под Linux. Управление VPN, DHCP, системными сервисами и бэкапом — всё через браузер в локальной сети.

Self-hosted, личный инструмент. Работает на реальном домашнем роутере (проверено на Debian/Ubuntu).

## Что умеет

- **AmneziaWG VPN** — запуск и остановка службы, просмотр активных пиров, маршрутизация по MAC-адресам
- **DHCP (dnsmasq)** — редактирование статических записей с автоматической группировкой по сегментам сети
- **Hotlist-файлы маршрутизации** — управление списками (сети Telegram, домены Figma и др.) через веб-интерфейс
- **Системные сервисы** — мониторинг состояния через systemd и ручной перезапуск из браузера
- **Диагностика и обслуживание** — захват трафика по MAC-адресу, запуск резервного копирования системы

## Стек

Python · FastAPI · Jinja2 · systemd · AmneziaWG · dnsmasq

## Развёртывание

Панель рассчитана на запуск как systemd-сервис на самом роутере.

1. Скопировать проект на роутер и установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```
2. Задать настройки:
   - `config.yaml` — пути, сегменты сети, список сервисов и hotlist-файлов
   - `.env` — секреты и параметры окружения
3. Зарегистрировать и запустить systemd-юнит:
   ```bash
   sudo systemctl enable --now home-router-panel
   ```

После запуска панель доступна по адресу роутера в локальной сети.

## Автор

Павел Найдёнов — [meteopavel.space](https://meteopavel.space)
