from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AppConfig:
    """Small wrapper around YAML config with project-root path resolution."""

    data: dict[str, Any]
    root: Path = PROJECT_ROOT

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def path(self, path: str, default: str = "") -> Path:
        value = self.get(path, default)
        candidate = Path(str(value))
        if candidate.is_absolute():
            return candidate
        return self.root / candidate


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "default.yaml"
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return AppConfig(data=data, root=PROJECT_ROOT)
