from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG_NAME, _load_mapping


def write_config_mapping(path: str | Path, data: dict[str, Any]) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_dump_simple_yaml(data), encoding="utf-8")
    return output


def update_config_values(repo: str | Path, values: dict[str, Any]) -> Path:
    repo_path = Path(repo).resolve()
    config_path = repo_path / DEFAULT_CONFIG_NAME
    data: dict[str, Any] = {}
    if config_path.exists():
        data = _load_mapping(config_path)
    data.update(values)
    return write_config_mapping(config_path, data)


def append_config_list_values(repo: str | Path, key: str, values: list[str], replace: bool = False) -> Path:
    repo_path = Path(repo).resolve()
    config_path = repo_path / DEFAULT_CONFIG_NAME
    data: dict[str, Any] = {}
    if config_path.exists():
        data = _load_mapping(config_path)
    current = [] if replace else _as_string_list(data.get(key))
    for value in values:
        if value not in current:
            current.append(value)
    data[key] = current
    return write_config_mapping(config_path, data)


def _dump_simple_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_quote(item)}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif value is None:
            lines.append(f"{key}: ''")
        else:
            lines.append(f"{key}: {_quote(value)}")
    lines.append("")
    return "\n".join(lines)


def _quote(value: Any) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return "''"
    # JSON quoting keeps Windows backslashes safe and is valid YAML.
    return json.dumps(text, ensure_ascii=False)


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
