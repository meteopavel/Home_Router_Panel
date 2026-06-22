"""Чтение и запись hotlist-файлов zapret (hosts, exclude)."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class HotlistContent:
    """Содержимое одного hotlist-файла."""

    name: str
    path: str
    lines: list[str]
    text: str


def get_hotlists_config(config: dict) -> list[dict]:
    """Возвращает список {name, path} для всех hotlist'ов из конфига."""
    hotlists = config.get("hotlists", {})
    return [{"name": name, "path": path} for name, path in hotlists.items()]


def read_hotlist(config: dict, name: str) -> HotlistContent | None:
    """Читает hotlist по имени. Возвращает None если имя не найдено в конфиге."""
    hotlists = config.get("hotlists", {})
    if name not in hotlists:
        return None

    path = hotlists[name]
    content = Path(path).read_text(encoding="utf-8", errors="replace")

    return HotlistContent(
        name=name,
        path=path,
        lines=content.splitlines(),
        text=content,
    )


def write_hotlist(config: dict, name: str, content: str) -> None:
    """Записывает содержимое hotlist-файла, нормализует переносы строк.

    Вызывает ValueError если имя не найдено в конфиге.
    """
    hotlists = config.get("hotlists", {})
    if name not in hotlists:
        raise ValueError(f"Hotlist not found: {name}")

    path = Path(hotlists[name])
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalized, encoding="utf-8")
