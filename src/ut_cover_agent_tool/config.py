from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_NAME = ".ut-cover.yaml"


@dataclass(frozen=True)
class ToolConfig:
    test_command: str
    coverage_command: str
    coverage_report: str
    source_dirs: list[str]
    test_dirs: list[str]
    exclude: list[str]
    report_dir: str
    config_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_command": self.test_command,
            "coverage_command": self.coverage_command,
            "coverage_report": self.coverage_report,
            "source_dirs": self.source_dirs,
            "test_dirs": self.test_dirs,
            "exclude": self.exclude,
            "report_dir": self.report_dir,
            "config_path": self.config_path,
        }


DEFAULT_CONFIG: dict[str, Any] = {
    "test_command": "",
    "coverage_command": "",
    "coverage_report": "coverage.json",
    "source_dirs": ["src"],
    "test_dirs": ["tests"],
    "exclude": [],
    "report_dir": ".ut-cover/reports",
}


def load_config(repo: str | Path = ".", config_path: str | Path | None = None) -> ToolConfig:
    repo_path = Path(repo).resolve()
    selected_path = Path(config_path).resolve() if config_path else repo_path / DEFAULT_CONFIG_NAME
    data = dict(DEFAULT_CONFIG)

    if selected_path.exists():
        loaded = _load_mapping(selected_path)
        data.update({key: value for key, value in loaded.items() if value is not None})
        path_text: str | None = str(selected_path)
    else:
        path_text = None

    return ToolConfig(
        test_command=str(data.get("test_command") or ""),
        coverage_command=str(data.get("coverage_command") or ""),
        coverage_report=str(data.get("coverage_report") or "coverage.json"),
        source_dirs=_string_list(data.get("source_dirs"), ["src"]),
        test_dirs=_string_list(data.get("test_dirs"), ["tests"]),
        exclude=_string_list(data.get("exclude"), []),
        report_dir=str(data.get("report_dir") or ".ut-cover/reports"),
        config_path=path_text,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    if raw.lstrip().startswith("{"):
        parsed = json.loads(raw)
    else:
        try:
            import yaml
        except ImportError:
            parsed = _parse_simple_yaml(raw)
        else:
            parsed = yaml.safe_load(raw)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return parsed


def _string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError(f"Expected string or list of strings, got {type(value).__name__}")


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    """Small fallback parser for the example config shape when PyYAML is unavailable."""
    result: dict[str, Any] = {}
    current_key: str | None = None
    for original_line in raw.splitlines():
        line = original_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_key:
            result.setdefault(current_key, []).append(_strip_quotes(line[4:].strip()))
            continue
        if ":" not in line:
            raise ValueError(f"Unsupported config line: {original_line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            result[key] = []
        elif value.startswith("[") and value.endswith("]"):
            items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            result[key] = [_strip_quotes(item) for item in items]
        else:
            result[key] = _strip_quotes(value)
    return result


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value
