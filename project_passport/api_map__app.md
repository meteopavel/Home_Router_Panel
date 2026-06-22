# API map: app

Просканировано Python-файлов: 7
Включено в карту: 6
Пропущено без значимой API-информации: 1

Сводная статистика:
- модулей: 6
- классов: 0
- dataclass: 4
- функций: 68
- методов: 0
- констант: 19

---

# app/amnezia.py

Константы:
- `SUDO = '/usr/bin/sudo'`
- `HELPER = '/usr/local/sbin/home-router-awg-config'`
- `AWG_CONFIG_DIR = Path('/etc/home-router-panel/awg')`
- `LISTS_CONFIG_FILE = AWG_CONFIG_DIR / 'lists_config.json'`
- `_DEFAULT_LISTS = [{'key': 'tg_nets', 'title': 'Telegram сети', 'hint': 'IPv4 адреса и CIDR-блоки, по одному на строк…`
- `_KEY_RE = re.compile('^[a-z][a-z0-9_]{0,31}$')`
- `DNSMASQ_LEASES = Path('/var/lib/misc/dnsmasq.leases')`

Функции:

- `load_lists_config() -> list[dict]`
  Return list of {key, title, hint} dicts. Falls back to defaults if file absent.

- `save_lists_config(lists: list[dict]) -> None`
  Нет докстринга.

- `get_list_meta() -> dict`
  Return {key: {title, hint}} dict for template use.

- `create_list(key: str, title: str, hint: str) -> tuple[bool, str]`
  Нет докстринга.

- `update_list_meta(key: str, title: str, hint: str, new_key: str = '') -> tuple[bool, str]`
  Нет докстринга.

- `delete_list(key: str) -> tuple[bool, str]`
  Нет докстринга.

- `_run_helper(*args, timeout: int = 15) -> subprocess.CompletedProcess`
  Нет докстринга.

- `get_awg_status() -> dict`
  Нет докстринга.

- `get_awg_show() -> Optional[str]`
  Нет докстринга.

- `run_awg_action(action: str) -> tuple[bool, str]`
  Нет докстринга.

- `get_diagnostics() -> Optional[str]`
  Нет докстринга.

- `_read_dnsmasq_leases() -> dict[str, str]`
  Return MAC→hostname map from dnsmasq leases file.

- `get_lan_devices() -> list[dict]`
  Нет докстринга.

- `check_route(target: str) -> str`
  Нет докстринга.

- `_list_path(name: str) -> Path`
  Нет докстринга.

- `read_awg_list(name: str) -> str`
  Нет докстринга.

- `write_awg_list(name: str, content: str) -> None`
  Нет докстринга.

- `add_mac_to_vpn(mac: str) -> bool`
  Нет докстринга.

---

# app/config.py

Константы:
- `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- `CONFIG_PATH = PROJECT_ROOT / 'config.yaml'`

Функции:

- `load_config() -> dict[str, Any]`
  Нет докстринга.

---

# app/dnsmasq.py

Константы:
- `LEASES_FILE = Path('/var/lib/misc/dnsmasq.leases')`
- `STATIC_FILE = Path('/etc/home-router-panel/awg/dnsmasq-static.conf')`
- `_HOSTNAME_RE = re.compile('^[a-zA-Z0-9\\-]{1,63}$')`
- `_IP_RE = re.compile('^(\\d{1,3}\\.){3}\\d{1,3}$')`
- `DNSMASQ_D = Path('/etc/dnsmasq.d')`
- `_IP_GROUPS: list[tuple[int, int, str]] = [(1, 9, 'Сетевое оборудование'), (10, 19, 'Компьютеры'), (20, 39, 'IoT'), (40, 49, 'Медиа'), (50, 5…`
- `IP_GROUP_NAMES: list[str] = list(dict.fromkeys((n for _, _, n in _IP_GROUPS)))`

Классы:

- `Lease [dataclass]`
  Нет докстринга.
  Поля:
  - `expiry: str`
  - `ts: int`
  - `mac: str`
  - `ip: str`
  - `hostname: str`
  - `client_id: str`

- `StaticEntry [dataclass]`
  Нет докстринга.
  Поля:
  - `mac: str`
  - `ip: str`
  - `hostname: str`

Функции:

- `validate_entry(mac: str, ip: str, hostname: str) -> str | None`
  Return error string if invalid, None if ok.

- `_test_config() -> tuple[bool, str]`
  Run dnsmasq --test to validate current config. Returns (ok, output).

- `read_leases() -> list[Lease]`
  Нет докстринга.

- `read_system_static() -> list[dict]`
  Read dhcp-host entries from /etc/dnsmasq.d/*.conf (read-only, for display).

- `read_static() -> list[StaticEntry]`
  Нет докстринга.

- `write_static(entries: list[StaticEntry]) -> tuple[bool, str]`
  Write static entries. Returns (ok, error_or_empty).

- `add_static(mac: str, ip: str, hostname: str) -> tuple[bool, str]`
  Add or update entry. Returns (ok, error_or_empty).

- `remove_static(mac: str, hostname: str = '') -> tuple[bool, str]`
  Нет докстринга.

- `reload_dnsmasq() -> tuple[bool, str]`
  Нет докстринга.

- `restart_dnsmasq() -> tuple[bool, str]`
  Нет докстринга.

- `get_ip_group(ip: str) -> str`
  Нет докстринга.

- `group_static_entries(entries: list[StaticEntry]) -> list[dict]`
  Нет докстринга.

- `get_dnsmasq_state() -> str`
  Нет докстринга.

---

# app/hotlists.py

Классы:

- `HotlistContent [dataclass]`
  Нет докстринга.
  Поля:
  - `name: str`
  - `path: str`
  - `lines: list[str]`
  - `text: str`

Функции:

- `get_hotlists_config(config: dict) -> list[dict]`
  Нет докстринга.

- `read_hotlist(config: dict, name: str) -> HotlistContent | None`
  Нет докстринга.

- `write_hotlist(config: dict, name: str, content: str) -> None`
  Нет докстринга.

---

# app/main.py

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
  Нет докстринга.

- `_amnezia_context(request: Request, target: str = '', msg: str = '', error: str = '') -> dict`
  Нет докстринга.

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
  Нет докстринга.

- `dnsmasq_view(request: Request, msg: str = '', edit: str = '', edit_host: str = '', pin: str = '')`
  Нет докстринга.

- `_dnsmasq_response(request: Request, error: str = '', msg: str = '', edit_mac: str = '', edit_host: str = '', pin_mac: str = '')`
  Нет докстринга.

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

Классы:

- `ServiceStatus [dataclass]`
  Нет докстринга.
  Поля:
  - `key: str`
  - `name: str`
  - `unit: str`
  - `state: str`
  - `description: str`
  - `is_active: bool`

Функции:

- `find_systemctl() -> str | None`
  Нет докстринга.

- `get_systemd_service_state(unit: str) -> str`
  Нет докстринга.

- `get_services_status(config: dict) -> list[ServiceStatus]`
  Нет докстринга.

- `get_service_unit(config: dict, service_name: str) -> str | None`
  Нет докстринга.

- `restart_service(config: dict, service_name: str) -> subprocess.CompletedProcess`
  Нет докстринга.