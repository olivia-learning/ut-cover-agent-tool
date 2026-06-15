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
    unit_test_include: list[str]
    unit_test_exclude: list[str]
    dt_test_patterns: list[str]
    preferred_test_roots: list[str]
    coverage_threshold: float | None
    changed_files_coverage_threshold: float | None
    coverage_fail_below_threshold: bool
    coverage_unknown_action: str
    execution_mode: str
    remote_backend: str
    remote_workspace_root: str
    remote_build_command: str
    remote_dt_command: str
    remote_artifacts: list[str]
    sync_include: list[str]
    sync_exclude: list[str]
    remote_clean_before_sync: bool
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
            "unit_test_include": self.unit_test_include,
            "unit_test_exclude": self.unit_test_exclude,
            "dt_test_patterns": self.dt_test_patterns,
            "preferred_test_roots": self.preferred_test_roots,
            "coverage_threshold": self.coverage_threshold,
            "changed_files_coverage_threshold": self.changed_files_coverage_threshold,
            "coverage_fail_below_threshold": self.coverage_fail_below_threshold,
            "coverage_unknown_action": self.coverage_unknown_action,
            "execution_mode": self.execution_mode,
            "remote_backend": self.remote_backend,
            "remote_workspace_root": self.remote_workspace_root,
            "remote_build_command": self.remote_build_command,
            "remote_dt_command": self.remote_dt_command,
            "remote_artifacts": self.remote_artifacts,
            "sync_include": self.sync_include,
            "sync_exclude": self.sync_exclude,
            "remote_clean_before_sync": self.remote_clean_before_sync,
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
    "unit_test_include": [],
    "unit_test_exclude": [],
    "dt_test_patterns": [
        "*integration*",
        "*e2e*",
        "*system*",
        "*dt*",
        "*device*",
        "*driver*",
        "*hardware*",
        "*scenario*",
        "*acceptance*",
    ],
    "preferred_test_roots": [],
    "coverage_threshold": None,
    "changed_files_coverage_threshold": None,
    "coverage_fail_below_threshold": True,
    "coverage_unknown_action": "warn",
    "execution_mode": "local",
    "remote_backend": "ai_ssh_mcp",
    "remote_workspace_root": "/tmp/ut-cover",
    "remote_build_command": "",
    "remote_dt_command": "",
    "remote_artifacts": ["coverage.xml", "coverage.json", "build.log", "dt.log"],
    "sync_include": ["**/*"],
    "sync_exclude": [
        ".git/**",
        ".venv/**",
        "venv/**",
        "node_modules/**",
        "build/**",
        "dist/**",
        ".ut-cover/**",
        "__pycache__/**",
    ],
    "remote_clean_before_sync": True,
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
        unit_test_include=_string_list(data.get("unit_test_include"), []),
        unit_test_exclude=_string_list(data.get("unit_test_exclude"), []),
        dt_test_patterns=_string_list(data.get("dt_test_patterns"), DEFAULT_CONFIG["dt_test_patterns"]),
        preferred_test_roots=_string_list(data.get("preferred_test_roots"), []),
        coverage_threshold=_optional_float(data.get("coverage_threshold")),
        changed_files_coverage_threshold=_optional_float(data.get("changed_files_coverage_threshold")),
        coverage_fail_below_threshold=_bool(data.get("coverage_fail_below_threshold"), True),
        coverage_unknown_action=_choice(
            str(data.get("coverage_unknown_action") or "warn"),
            {"warn", "fail"},
            "coverage_unknown_action",
        ),
        execution_mode=_choice(str(data.get("execution_mode") or "local"), {"local", "remote"}, "execution_mode"),
        remote_backend=str(data.get("remote_backend") or "ai_ssh_mcp"),
        remote_workspace_root=str(data.get("remote_workspace_root") or "/tmp/ut-cover"),
        remote_build_command=str(data.get("remote_build_command") or ""),
        remote_dt_command=str(data.get("remote_dt_command") or ""),
        remote_artifacts=_string_list(data.get("remote_artifacts"), DEFAULT_CONFIG["remote_artifacts"]),
        sync_include=_string_list(data.get("sync_include"), DEFAULT_CONFIG["sync_include"]),
        sync_exclude=_string_list(data.get("sync_exclude"), DEFAULT_CONFIG["sync_exclude"]),
        remote_clean_before_sync=_bool(data.get("remote_clean_before_sync"), True),
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


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if number < 0 or number > 100:
        raise ValueError("coverage thresholds must be between 0 and 100")
    return number


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def _choice(value: str, allowed: set[str], field: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{field} must be one of: {choices}")
    return normalized


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
