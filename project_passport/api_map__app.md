# API map: app

Просканировано Python-файлов: 9
Включено в карту: 8
Пропущено без значимой API-информации: 1

Сводная статистика:
- модулей: 8
- классов: 0
- dataclass: 4
- функций: 103
- методов: 0
- констант: 32

---

# app/amnezia.py

Модуль:
Управление AmneziaWG: конфигурация списков, статус и контроль AWG, LAN-устройства.

Константы:
- `SUDO = '/usr/bin/sudo'`
- `HELPER = '/usr/local/sbin/home-router-awg-config'`
- `AWG_CONFIG_DIR = Path('/etc/home-router-panel/awg')`
- `LISTS_CONFIG_FILE = AWG_CONFIG_DIR / 'lists_config.json'`
- `DNSMASQ_LEASES = Path('/var/lib/misc/dnsmasq.leases')`
- `_DEFAULT_LISTS = [{'key': 'tg_nets', 'title': 'Telegram сети', 'hint': 'IPv4 адреса и CIDR-блоки, по одному на строк…`
- `_KEY_RE = re.compile('^[a-z][a-z0-9_]{0,31}$')`

Функции:

- `_run_helper(*args, timeout: int = 15) -> subprocess.CompletedProcess`
  Запускает home-router-awg-config через sudo. Возвращает CompletedProcess-подобный объект.

- `_list_path(name: str) -> Path`
  Возвращает путь к файлу списка. Вызывает ValueError если ключ не зарегистрирован.

- `_read_dnsmasq_leases() -> dict[str, str]`
  Читает файл аренд dnsmasq, возвращает словарь MAC → hostname.

- `load_lists_config() -> list[dict]`
  Читает lists_config.json. Возвращает дефолтный список если файл отсутствует или повреждён.

- `save_lists_config(lists: list[dict]) -> None`
  Сохраняет метаданные списков в lists_config.json.

- `get_list_meta() -> dict`
  Возвращает словарь {ключ: {title, hint}} для использования в шаблонах.

- `create_list(key: str, title: str, hint: str) -> tuple[bool, str]`
  Создаёт новый список и пустой txt-файл. Возвращает (ok, ошибка_или_пусто).

- `update_list_meta(key: str, title: str, hint: str, new_key: str = '') -> tuple[bool, str]`
  Обновляет название/подсказку списка, при необходимости переименовывает ключ и файл.

- `reorder_lists(keys: list[str]) -> None`
  Переставляет списки в lists_config.json согласно переданному порядку ключей.

- `delete_list(key: str) -> tuple[bool, str]`
  Удаляет список из конфига и переименовывает файл в .txt.deleted.

- `read_awg_list(name: str) -> str`
  Читает содержимое txt-файла списка. Возвращает пустую строку если файл не существует.

- `write_awg_list(name: str, content: str) -> None`
  Записывает содержимое в txt-файл списка, сохраняет .bak-резервную копию.

- `add_mac_to_vpn(mac: str) -> bool`
  Добавляет MAC-адрес в vpn_device_macs.txt. Возвращает False при некорректном MAC.

- `get_awg_status() -> dict`
  Возвращает словарь со статусом AWG-сервиса и интерфейса от helper-скрипта.

- `get_awg_show() -> Optional[str]`
  Возвращает вывод awg show awg0 или None если helper недоступен.

- `run_awg_action(action: str) -> tuple[bool, str]`
  Выполняет одно из допустимых действий: start / stop / restart / apply.

- `get_diagnostics() -> Optional[str]`
  Возвращает диагностический вывод от helper-скрипта или сообщение об ошибке.

- `get_lan_devices() -> list[dict]`
  Возвращает список {ip, mac, state, hostname} из ARP-таблицы через helper.

- `check_route(target: str) -> str`
  Проверяет маршрут для домена или IP через helper. Возвращает текстовый вывод.

- `_fmt_bytes(n: int) -> str`
  Форматирует байты в читаемый вид: B / KiB / MiB / GiB.

- `get_awg_traffic() -> dict`
  Читает статистику awg0 из vnstat. Возвращает dict с полями для шаблона.

---

# app/claude.py

Модуль:
Вкладка Claude → GLM: редирект api.anthropic.com на GLM (z.ai) для выбранных MAC.

Перехват происходит на сетевом уровне (dnsmasq ipset + iptables DNAT per-MAC —
см. scripts/home-router-claude-gateway). Этот модуль отвечает за:
  - управление списком MAC (/etc/home-router-panel/claude/macs.txt) из UI;
  - прокси POST /v1/messages → https://api.z.ai/api/anthropic/v1/messages
    с маппингом модели (haiku→glm-4.7, sonnet/opus→glm-5.2) и z.ai-ключом.

Остальные пути api.anthropic.com (auth/OAuth/телеметрия) nginx отдаёт настоящему
Anthropic сам (location / → proxy_pass https://api.anthropic.com) — в Python catch-all
не нужен, поэтому с UI-роутами панели конфликтов нет.

Константы:
- `CONF_DIR = Path('/etc/home-router-panel/claude')`
- `MACS_FILE = CONF_DIR / 'macs.txt'`
- `ZAI_KEY_FILE = CONF_DIR / 'zai.key'`
- `HELPER = '/usr/local/sbin/home-router-claude-gateway'`
- `ZAI_BASE = 'https://api.z.ai/api/anthropic'`
- `ANTHROPIC_VERSION_DEFAULT = '2023-06-01'`
- `DEFAULT_GLM_MODEL = 'glm-5.2'`
- `MODEL_PREFIX_MAP: tuple[tuple[str, str], ...] = (('haiku', 'glm-4.7'), ('sonnet', 'glm-5.2'), ('opus', 'glm-5.2'))`
- `PROJECT_ROOT = Path(__file__).resolve().parent.parent`

Функции:

- `read_macs() -> list[str]`
  Список MAC-адресов, для которых api.anthropic.com уходит в GLM.

- `write_macs(macs: list[str]) -> None`
  Нет докстринга.

- `helper_available() -> bool`
  Нет докстринга.

- `apply_redirect() -> tuple[bool, str]`
  Перестраивает ipset + mangle-exempt + DNAT через sudo-helper.

- `get_status() -> dict`
  Нет докстринга.

- `_map_model(model: str) -> str`
  Нет докстринга.

- `_read_zai_key() -> str | None`
  Нет докстринга.

- `_forward_to_zai(request: Request) -> StreamingResponse`
  POST /v1/messages* → z.ai: маппинг модели, z.ai-ключ, стриминг ответа.

- `_context(request: Request, msg: str = '', error: str = '') -> dict`
  Нет докстринга.

- `claude_view(request: Request, msg: str = '', error: str = '')`
  Нет докстринга.

- `claude_macs_save(request: Request, macs: list[str] = Form(default=[]))`
  Нет докстринга.

- `claude_macs_save_apply(request: Request, macs: list[str] = Form(default=[]))`
  Нет докстринга.

- `claude_messages(request: Request)`
  Anthropic Messages API → GLM (z.ai).

- `claude_count_tokens(request: Request)`
  Счётчик токенов — тоже через GLM.

---

# app/config.py

Модуль:
Загрузка конфигурации приложения из config.yaml.

Константы:
- `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- `CONFIG_PATH = PROJECT_ROOT / 'config.yaml'`

Функции:

- `load_config() -> dict[str, Any]`
  Читает config.yaml и возвращает словарь конфигурации.
  
  Вызывает RuntimeError если файл не найден.
  Возвращает пустой dict если файл пустой.

---

# app/dnsmasq.py

Модуль:
Работа с dnsmasq: статические резервации, аренды DHCP, статус сервиса, ARP.

Константы:
- `LEASES_FILE = Path('/var/lib/misc/dnsmasq.leases')`
- `STATIC_FILE = Path('/etc/home-router-panel/awg/dnsmasq-static.conf')`
- `DNSMASQ_D = Path('/etc/dnsmasq.d')`
- `_HOSTNAME_RE = re.compile('^[a-zA-Z0-9\\-]{1,63}$')`
- `_IP_RE = re.compile('^(\\d{1,3}\\.){3}\\d{1,3}$')`
- `_IP_GROUPS: list[tuple[int, int, str]] = [(1, 9, 'Сетевое оборудование'), (10, 19, 'Компьютеры'), (20, 39, 'IoT'), (40, 49, 'Медиа'), (50, 5…`
- `IP_GROUP_NAMES: list[str] = list(dict.fromkeys((n for _, _, n in _IP_GROUPS)))`

Классы:

- `Lease [dataclass]`
  Одна запись из файла аренд dnsmasq.
  Поля:
  - `expiry: str`
  - `ts: int`
  - `mac: str`
  - `ip: str`
  - `hostname: str`
  - `client_id: str`

- `StaticEntry [dataclass]`
  Статическая DHCP-резервация из управляемого файла панели.
  Поля:
  - `mac: str`
  - `ip: str`
  - `hostname: str`
  - `mac_from_lease: bool = False`

Функции:

- `_test_config() -> tuple[bool, str]`
  Запускает dnsmasq --test для проверки конфига. Возвращает (ok, вывод).

- `validate_entry(mac: str, ip: str, hostname: str) -> str | None`
  Проверяет корректность полей записи. Возвращает строку ошибки или None.

- `read_leases() -> list[Lease]`
  Читает файл аренд dnsmasq, возвращает список отсортированный по IP.

- `read_system_static() -> list[dict]`
  Читает dhcp-host записи из /etc/dnsmasq.d/*.conf. Только для отображения, не редактируется.

- `read_static() -> list[StaticEntry]`
  Читает управляемый файл резерваций dnsmasq-static.conf, сортирует по IP.

- `write_static(entries: list[StaticEntry]) -> tuple[bool, str]`
  Записывает список резерваций в файл. Проверяет конфиг через dnsmasq --test, при ошибке откатывает.

- `add_static(mac: str, ip: str, hostname: str) -> tuple[bool, str]`
  Добавляет или обновляет резервацию. Возвращает (ok, ошибка_или_пусто).

- `remove_static(mac: str, hostname: str = '') -> tuple[bool, str]`
  Удаляет резервацию по MAC или имени устройства. Возвращает (ok, ошибка_или_пусто).

- `get_dnsmasq_state() -> str`
  Возвращает строку состояния сервиса dnsmasq (active / inactive / failed / unknown).

- `reload_dnsmasq() -> tuple[bool, str]`
  Отправляет SIGHUP dnsmasq (применяет конфиг без обрыва аренд). Возвращает (ok, сообщение).

- `restart_dnsmasq() -> tuple[bool, str]`
  Полный перезапуск dnsmasq. Сбрасывает все аренды. Возвращает (ok, сообщение).

- `get_ip_group(ip: str) -> str`
  Возвращает название группы по последнему октету IP или пустую строку.

- `group_static_entries(entries: list[StaticEntry]) -> list[dict]`
  Группирует записи по диапазонам IP. Возвращает список {name, lo, hi, entries}.

- `get_arp_online() -> tuple[set[str], set[str]]`
  Возвращает (online_macs, online_ips) из ARP-таблицы интерфейса enp2s0.
  
  Устройство считается онлайн если имеет lladdr и состояние не FAILED.
  Состояния REACHABLE / STALE / DELAY / PROBE — онлайн.
  После отключения запись переходит в FAILED примерно за 1–3 минуты.
  При ошибке вызова ip возвращает два пустых множества.

---

# app/hotlists.py

Модуль:
Чтение и запись hotlist-файлов zapret (hosts, exclude).

Классы:

- `HotlistContent [dataclass]`
  Содержимое одного hotlist-файла.
  Поля:
  - `name: str`
  - `path: str`
  - `lines: list[str]`
  - `text: str`

Функции:

- `get_hotlists_config(config: dict) -> list[dict]`
  Возвращает список {name, path} для всех hotlist'ов из конфига.

- `read_hotlist(config: dict, name: str) -> HotlistContent | None`
  Читает hotlist по имени. Возвращает None если имя не найдено в конфиге.

- `write_hotlist(config: dict, name: str, content: str) -> None`
  Записывает содержимое hotlist-файла, нормализует переносы строк.
  
  Вызывает ValueError если имя не найдено в конфиге.

---

# app/main.py

Модуль:
Маршруты FastAPI: обзор, zapret, AmneziaWG, dnsmasq, бэкап, SSE.

Константы:
- `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- `STATIC_DIR = PROJECT_ROOT / 'static'`
- `TEMPLATES_DIR = PROJECT_ROOT / 'templates'`

Функции:

- `index(request: Request)`
  Главная страница: карточки обзора и статусы сервисов.

- `zapret_view(request: Request)`
  Вкладка zapret: список hotlist-файлов и статус сервиса.

- `hotlist_view(name: str)`
  Перенаправляет на страницу редактирования hotlist.

- `hotlist_edit_view(request: Request, name: str)`
  Редактирование hotlist-файла zapret.

- `hotlist_edit_save(request: Request, name: str, content: str = Form(default=''))`
  Сохраняет hotlist и перезапускает zapret.

- `_parse_vpn_macs(content: str) -> set[str]`
  Парсит содержимое vpn_device_macs.txt, возвращает множество MAC-адресов (строчные).

- `_amnezia_context(request: Request, target: str = '', msg: str = '', error: str = '') -> dict`
  Собирает контекст шаблона amnezia.html: статус AWG, списки, резервации, VPN-MACs.

- `amnezia_view(request: Request, target: str = '', msg: str = '', error: str = '')`
  Вкладка AmneziaWG: статус, списки, маршрутизация.

- `amnezia_service_action(action: str)`
  Выполняет действие с AWG-сервисом: start / stop / restart / apply.

- `amnezia_list_save(name: str, content: str = Form(default=''))`
  Сохраняет содержимое одного AWG-списка.

- `amnezia_list_create(request: Request, key: str = Form(default=''), title: str = Form(default=''), hint: str = Form(default=''))`
  Создаёт новый AWG-список (название, ключ, подсказка).

- `amnezia_list_delete(request: Request, key: str)`
  Удаляет AWG-список, переименовывает файл в .txt.deleted.

- `amnezia_list_meta_save(request: Request, key: str, title: str = Form(default=''), hint: str = Form(default=''), new_key: str = Form(default=''))`
  Сохраняет метаданные списка: название, подсказку, ключ.

- `amnezia_lists_reorder(request: Request)`
  Принимает JSON {keys: [...]} и переставляет списки в config.

- `amnezia_vpn_macs_save(request: Request, macs: list[str] = Form(default=[]))`
  Сохраняет выбранные MAC-адреса устройств для VPN-маршрутизации.

- `amnezia_add_mac(mac: str = Form(default=''))`
  Добавляет MAC-адрес в vpn_device_macs из LAN-списка.

- `service_restart(name: str)`
  Перезапускает systemd-сервис по ключу из config.yaml.

- `backup_run()`
  Запускает бэкап через home-router-backup, стримит на Mac.

- `capture_traffic(request: Request, mac: str = '', seconds: int = 15, count: int = 200)`
  Перехват трафика tcpdump по MAC-адресу на интерфейсе enp2s0.

- `_build_dnsmasq_context(**extra) -> dict`
  Собирает контекст шаблона dnsmasq.html: резервации, аренды, онлайн-статусы через ARP.

- `dnsmasq_view(request: Request, msg: str = '', edit: str = '', edit_host: str = '', pin: str = '')`
  Вкладка dnsmasq: резервации, аренды, онлайн-статусы устройств.

- `_dnsmasq_response(request: Request, error: str = '', msg: str = '', edit_mac: str = '', edit_host: str = '', pin_mac: str = '')`
  Рендерит dnsmasq.html с текущим контекстом и дополнительными параметрами.

- `dnsmasq_static_add(request: Request, mac: str = Form(default=''), ip: str = Form(default=''), hostname: str = Form(default=''))`
  Добавляет статическую DHCP-резервацию.

- `dnsmasq_static_update(request: Request, mac: str = Form(default=''), ip: str = Form(default=''), hostname: str = Form(default=''))`
  Обновляет существующую DHCP-резервацию.

- `dnsmasq_static_remove(request: Request, mac: str = Form(default=''), hostname: str = Form(default=''))`
  Удаляет статическую DHCP-резервацию по MAC или имени.

- `dnsmasq_service_reload()`
  AJAX: перезагружает dnsmasq (SIGHUP). Возвращает JSON {ok, error?}.

- `dnsmasq_service_restart()`
  AJAX: полный перезапуск dnsmasq. Возвращает JSON {ok, error?}.

- `dnsmasq_events()`
  SSE-поток онлайн-статусов: обновляется при изменении ARP или leases.

- `dnsmasq_ping(ip: str = '')`
  Пинг устройства по IP. Возвращает JSON {online: bool, ip: str}.

- `health()`
  Проверка доступности приложения.

- `awg_speed()`
  Возвращает текущую скорость awg0 в байт/с (два чтения /proc/net/dev с паузой 1 с).

- `tun0_speed()`
  Возвращает текущую скорость tun0 в байт/с.

- `_openvpn_context(request: Request, msg: str = '', error: str = '') -> dict`
  Нет докстринга.

- `openvpn_view(request: Request, msg: str = '')`
  Нет докстринга.

- `openvpn_service_action(request: Request, action: str = Form(default=''))`
  Нет докстринга.

- `openvpn_macs_save(request: Request, macs: list[str] = Form(default=[]))`
  Нет докстринга.

- `openvpn_macs_save_apply(request: Request, macs: list[str] = Form(default=[]))`
  Нет докстринга.

---

# app/openvpn.py

Модуль:
OpenVPN: статус сервиса openvpn@mailganer, управление, список разрешённых MAC.

Константы:
- `CONF_DIR = Path('/etc/home-router-panel/openvpn')`
- `VPN_MACS_FILE = CONF_DIR / 'vpn_device_macs.txt'`
- `SERVICE_UNIT = 'openvpn@mailganer'`
- `HELPER = '/usr/local/sbin/home-router-openvpn-routing'`

Функции:

- `get_openvpn_status() -> dict`
  Возвращает состояние сервиса openvpn@mailganer и наличие интерфейса tun0.

- `openvpn_action(action: str) -> tuple[bool, str]`
  Выполняет start/stop/restart для openvpn@mailganer через sudo.

- `read_vpn_macs() -> list[str]`
  Читает список MAC-адресов из vpn_device_macs.txt.

- `write_vpn_macs(macs: list[str]) -> None`
  Сохраняет список MAC-адресов в vpn_device_macs.txt.

- `apply_routing() -> tuple[bool, str]`
  Запускает скрипт маршрутизации через sudo.

- `helper_available() -> bool`
  Нет докстринга.

- `_fmt_bytes(n: int) -> str`
  Нет докстринга.

- `get_tun0_traffic() -> dict`
  Читает статистику tun0 из vnstat.

---

# app/services.py

Модуль:
Получение статусов и управление systemd-сервисами через systemctl.

Классы:

- `ServiceStatus [dataclass]`
  Статус одного systemd-сервиса из config.yaml.
  Поля:
  - `key: str`
  - `name: str`
  - `unit: str`
  - `state: str`
  - `description: str`
  - `is_active: bool`

Функции:

- `find_systemctl() -> str | None`
  Возвращает путь к systemctl или None если не найден.

- `get_systemd_service_state(unit: str) -> str`
  Возвращает строку состояния юнита: active / inactive / failed / unknown / timeout.

- `get_service_unit(config: dict, service_name: str) -> str | None`
  Возвращает имя юнита для сервиса из конфига или None если сервис не найден.

- `get_services_status(config: dict) -> list[ServiceStatus]`
  Возвращает список статусов всех сервисов из config.yaml.

- `restart_service(config: dict, service_name: str) -> subprocess.CompletedProcess`
  Перезапускает сервис через sudo systemctl restart.
  
  Вызывает ValueError если сервис не найден в конфиге.