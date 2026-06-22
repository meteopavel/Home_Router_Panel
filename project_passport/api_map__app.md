# API map: app

Просканировано Python-файлов: 7
Включено в карту: 6
Пропущено без значимой API-информации: 1

Сводная статистика:
- модулей: 6
- классов: 0
- dataclass: 4
- функций: 69
- методов: 0
- констант: 19

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
  Нет докстринга.

- `zapret_view(request: Request)`
  Нет докстринга.

- `hotlist_view(name: str)`
  Нет докстринга.

- `hotlist_edit_view(request: Request, name: str)`
  Нет докстринга.

- `hotlist_edit_save(request: Request, name: str, content: str = Form(default=''))`
  Нет докстринга.

- `_parse_vpn_macs(content: str) -> set[str]`
  Парсит содержимое vpn_device_macs.txt, возвращает множество MAC-адресов (строчные).

- `_amnezia_context(request: Request, target: str = '', msg: str = '', error: str = '') -> dict`
  Собирает контекст шаблона amnezia.html: статус AWG, списки, резервации, VPN-MACs.

- `amnezia_view(request: Request, target: str = '', msg: str = '', error: str = '')`
  Нет докстринга.

- `amnezia_service_action(action: str)`
  Нет докстринга.

- `amnezia_list_save(name: str, content: str = Form(default=''))`
  Нет докстринга.

- `amnezia_list_create(request: Request, key: str = Form(default=''), title: str = Form(default=''), hint: str = Form(default=''))`
  Нет докстринга.

- `amnezia_list_delete(request: Request, key: str)`
  Нет докстринга.

- `amnezia_list_meta_save(request: Request, key: str, title: str = Form(default=''), hint: str = Form(default=''), new_key: str = Form(default=''))`
  Нет докстринга.

- `amnezia_vpn_macs_save(request: Request, macs: list[str] = Form(default=[]))`
  Нет докстринга.

- `amnezia_add_mac(mac: str = Form(default=''))`
  Нет докстринга.

- `service_restart(name: str)`
  Нет докстринга.

- `backup_run()`
  Нет докстринга.

- `capture_traffic(request: Request, mac: str = '', seconds: int = 15, count: int = 200)`
  Нет докстринга.

- `_build_dnsmasq_context(**extra) -> dict`
  Собирает контекст шаблона dnsmasq.html: резервации, аренды, онлайн-статусы через ARP.

- `dnsmasq_view(request: Request, msg: str = '', edit: str = '', edit_host: str = '', pin: str = '')`
  Нет докстринга.

- `_dnsmasq_response(request: Request, error: str = '', msg: str = '', edit_mac: str = '', edit_host: str = '', pin_mac: str = '')`
  Рендерит dnsmasq.html с текущим контекстом и дополнительными параметрами.

- `dnsmasq_static_add(request: Request, mac: str = Form(default=''), ip: str = Form(default=''), hostname: str = Form(default=''))`
  Нет докстринга.

- `dnsmasq_static_update(request: Request, mac: str = Form(default=''), ip: str = Form(default=''), hostname: str = Form(default=''))`
  Нет докстринга.

- `dnsmasq_static_remove(request: Request, mac: str = Form(default=''), hostname: str = Form(default=''))`
  Нет докстринга.

- `dnsmasq_service_reload()`
  Нет докстринга.

- `dnsmasq_service_restart()`
  Нет докстринга.

- `dnsmasq_events()`
  Нет докстринга.

- `health()`
  Нет докстринга.

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