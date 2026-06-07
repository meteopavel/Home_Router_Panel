# Home Router Panel

Локальная веб-панель для управления домашним Linux-сервером, который используется как сетевой шлюз/роутер.

Проект создаётся как небольшой кастомный интерфейс для управления домашним трафиком без постоянной работы через терминал.

## Основные цели

- управление hotlist/hostlist для `zapret`;
- применение изменений без ручного захода в терминал;
- управление split routing через Amnezia VPN;
- просмотр статусов сетевых сервисов;
- локальный веб-интерфейс для домашней сети;
- простой деплой с GitHub на сервер.

## Планируемый стек

- Python;
- FastAPI;
- Jinja2 templates;
- systemd;
- GitHub Actions / простой pull-based deploy;
- Linux server.

## Предполагаемые возможности MVP

- просмотр и редактирование hotlist для `zapret`;
- кнопка применения изменений;
- просмотр статуса `zapret`;
- просмотр статуса Amnezia VPN;
- перезапуск нужных сервисов;
- запуск панели как `systemd`-сервиса;
- доступ только из локальной сети.

## Структура проекта

```text
Home_Router_Panel/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── services.py
│   ├── hotlists.py
│   └── routing.py
├── templates/
│   ├── base.html
│   └── index.html
├── static/
│   └── style.css
├── deploy/
│   ├── home-router-panel.service
│   └── deploy.sh
├── config.example.yaml
├── requirements.txt
├── README.md
└── .gitignore

