from dataclasses import dataclass
from pathlib import Path


@dataclass
class HotlistContent:
    name: str
    path: str
    lines: list[str]


def get_hotlists_config(config: dict) -> list[dict]:
    hotlists = config.get("hotlists", {})

    return [
        {
            "name": name,
            "path": path,
        }
        for name, path in hotlists.items()
    ]


def read_hotlist(config: dict, name: str) -> HotlistContent | None:
    hotlists = config.get("hotlists", {})

    if name not in hotlists:
        return None

    path = hotlists[name]
    file_path = Path(path)

    content = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return HotlistContent(
        name=name,
        path=path,
        lines=content.splitlines(),
    )