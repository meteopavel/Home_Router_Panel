"""Загрузка конфигурации приложения из config.yaml."""

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    """Читает config.yaml и возвращает словарь конфигурации.

    Вызывает RuntimeError если файл не найден.
    Возвращает пустой dict если файл пустой.
    """
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            "config.yaml not found. Copy config.example.yaml to config.yaml"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        return {}

    return data
