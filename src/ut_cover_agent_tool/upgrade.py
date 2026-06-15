from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .errors import UtCoverError


REQUIRED_AI_SSH_MCP_MIN_VERSION = "0.1.0"
UPGRADE_REPORT_DIR = ".ut-cover-upgrade"

EXCLUDED_OVERLAY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".ut-cover",
    ".ut-cover-upgrade",
    ".upgrade-backups",
}


def current_tool_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_upgrade_status(
    install_dir: str | Path | None = None,
    ut_zip: str | Path | None = None,
    ssh_zip: str | Path | None = None,
    zip_dir: str | Path | None = None,
    interaction_mode: str = "interactive",
) -> dict[str, Any]:
    root = Path(install_dir).resolve() if install_dir else current_tool_root()
    selected_zip_dir = _zip_dir(root, zip_dir, ut_zip)
    ut_zip_path = Path(ut_zip).resolve() if ut_zip else selected_zip_dir / "ut-cover-agent-tool.zip"
    ssh_zip_path = Path(ssh_zip).resolve() if ssh_zip else selected_zip_dir / "ai-ssh-mcp-tool.zip"
    ssh_info = detect_ai_ssh_mcp(root)
    ut_zip_info = read_zip_info(ut_zip_path, "ut-cover-agent-tool")
    ssh_zip_info = read_zip_info(ssh_zip_path, "ai-ssh-mcp")
    ssh_compatible = _version_gte(ssh_info.get("version"), REQUIRED_AI_SSH_MCP_MIN_VERSION)
    ssh_zip_available = bool(ssh_zip_info.get("exists"))

    next_action = "continue"
    if not ut_zip_info.get("exists"):
        next_action = "provide_ut_zip"
    elif not ssh_info.get("available"):
        next_action = "install_ai_ssh_mcp_from_zip" if ssh_zip_available else "provide_ai_ssh_mcp_zip"
    elif not ssh_compatible:
        if interaction_mode == "autonomous" and ssh_zip_available:
            next_action = "auto_upgrade_ai_ssh_mcp"
        else:
            next_action = "upgrade_ai_ssh_mcp_with_confirmation" if ssh_zip_available else "provide_ai_ssh_mcp_zip"

    return {
        "ok": next_action == "continue",
        "tool": "ut-cover-agent-tool",
        "current_version": __version__,
        "install_dir": str(root),
        "python": sys.executable,
        "interaction_mode": interaction_mode,
        "required_ai_ssh_mcp_min_version": REQUIRED_AI_SSH_MCP_MIN_VERSION,
        "ut_zip": ut_zip_info,
        "ai_ssh_mcp": {**ssh_info, "compatible": ssh_compatible},
        "ssh_zip": ssh_zip_info,
        "next_action": next_action,
    }


def upgrade_from_zip(
    install_dir: str | Path,
    ut_zip: str | Path,
    *,
    run_pip_install: bool = True,
) -> dict[str, Any]:
    root = _safe_install_dir(install_dir)
    zip_path = Path(ut_zip).resolve()
    if not zip_path.exists():
        raise UtCoverError(f"UT zip not found: {zip_path}")

    backup_dir = _backup_install_dir(root)
    with tempfile.TemporaryDirectory() as tmp:
        extracted = _extract_zip_root(zip_path, Path(tmp))
        _overlay_tree(extracted, root)

    pip_result = _pip_install(root) if run_pip_install else None
    report = {
        "ok": pip_result is None or pip_result.returncode == 0,
        "action": "upgrade_ut_cover",
        "install_dir": str(root),
        "ut_zip": str(zip_path),
        "backup_dir": str(backup_dir),
        "pip_install": _completed_process_to_dict(pip_result),
        "next_action": "continue" if pip_result is None or pip_result.returncode == 0 else "inspect_pip_error",
    }
    write_upgrade_report(root, report)
    return report


def upgrade_ai_ssh_mcp_from_zip(
    ssh_zip: str | Path,
    *,
    ssh_install_dir: str | Path | None = None,
    reference_install_dir: str | Path | None = None,
    run_pip_install: bool = True,
) -> dict[str, Any]:
    zip_path = Path(ssh_zip).resolve()
    if not zip_path.exists():
        raise UtCoverError(f"AI SSH MCP zip not found: {zip_path}")
    target = Path(ssh_install_dir).resolve() if ssh_install_dir else _infer_ai_ssh_mcp_root(reference_install_dir)
    if target is None:
        raise UtCoverError("Cannot infer ai_ssh_mcp install dir. Pass --ssh-install-dir.")
    target = _safe_install_dir(target)

    backup_dir = _backup_install_dir(target)
    with tempfile.TemporaryDirectory() as tmp:
        extracted = _extract_zip_root(zip_path, Path(tmp))
        _overlay_tree(extracted, target)

    pip_result = _pip_install(target) if run_pip_install else None
    report = {
        "ok": pip_result is None or pip_result.returncode == 0,
        "action": "upgrade_ai_ssh_mcp",
        "install_dir": str(target),
        "ssh_zip": str(zip_path),
        "backup_dir": str(backup_dir),
        "pip_install": _completed_process_to_dict(pip_result),
        "next_action": "restart_opencode" if pip_result is None or pip_result.returncode == 0 else "inspect_pip_error",
    }
    write_upgrade_report(target, report)
    return report


def read_zip_info(zip_path: str | Path, expected_tool: str) -> dict[str, Any]:
    path = Path(zip_path).resolve()
    if not path.exists():
        return {"exists": False, "path": str(path), "version": "missing"}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            manifest_name = next((name for name in names if name.endswith("ZIP_MANIFEST.json")), None)
            version_name = next((name for name in names if name.endswith("/VERSION") or name == "VERSION"), None)
            manifest = json.loads(archive.read(manifest_name).decode("utf-8")) if manifest_name else {}
            version = manifest.get("version")
            if not version and version_name:
                version = archive.read(version_name).decode("utf-8").strip()
    except Exception as exc:
        return {"exists": True, "path": str(path), "version": "unreadable", "error": str(exc)}
    return {
        "exists": True,
        "path": str(path),
        "tool": manifest.get("tool", expected_tool) if manifest else expected_tool,
        "version": version or "unknown",
        "manifest": manifest,
    }


def detect_ai_ssh_mcp(reference_install_dir: str | Path | None = None) -> dict[str, Any]:
    _ensure_possible_parent_src(reference_install_dir)
    try:
        module = importlib.import_module("ai_ssh_mcp")
    except Exception as exc:
        return {"available": False, "version": "missing", "error": str(exc), "install_dir": None}
    module_file = Path(getattr(module, "__file__", "")).resolve()
    version = getattr(module, "__version__", None) or "unknown"
    install_dir = _package_project_root(module_file)
    return {
        "available": True,
        "version": str(version),
        "install_dir": str(install_dir) if install_dir else str(module_file.parent),
        "module_file": str(module_file),
    }


def write_upgrade_report(install_dir: str | Path, report: dict[str, Any]) -> Path:
    root = Path(install_dir).resolve()
    output_dir = root / UPGRADE_REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "upgrade-report.json"
    md_path = output_dir / "upgrade-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_upgrade_markdown(report), encoding="utf-8")
    return json_path


def render_upgrade_markdown(report: dict[str, Any]) -> str:
    lines = ["# Upgrade Report", ""]
    lines.append(f"- OK: {report.get('ok')}")
    lines.append(f"- Action: `{report.get('action', 'status')}`")
    lines.append(f"- Next action: `{report.get('next_action', '')}`")
    for key in ["install_dir", "backup_dir", "ut_zip", "ssh_zip"]:
        if report.get(key):
            lines.append(f"- {key}: `{report.get(key)}`")
    pip_install = report.get("pip_install")
    if pip_install:
        lines.append(f"- pip exit code: {pip_install.get('returncode')}")
    lines.append("")
    return "\n".join(lines)


def _zip_dir(root: Path, zip_dir: str | Path | None, ut_zip: str | Path | None) -> Path:
    if zip_dir:
        return Path(zip_dir).resolve()
    if ut_zip:
        return Path(ut_zip).resolve().parent
    return root.parent


def _safe_install_dir(path: str | Path) -> Path:
    root = Path(path).resolve()
    if not root.exists():
        raise UtCoverError(f"Install dir does not exist: {root}")
    anchor = Path(root.anchor).resolve()
    blocked = {anchor, Path.home().resolve()}
    if root in blocked or len(root.parts) < 3:
        raise UtCoverError(f"Unsafe install dir: {root}")
    return root


def _backup_install_dir(root: Path) -> Path:
    backup_root = root.parent / ".upgrade-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{root.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copytree(root, backup, ignore=shutil.ignore_patterns(*EXCLUDED_OVERLAY_NAMES))
    return backup


def _extract_zip_root(zip_path: Path, tmp: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(tmp)
    children = [path for path in tmp.iterdir()]
    dirs = [path for path in children if path.is_dir()]
    if len(dirs) == 1:
        return dirs[0]
    for candidate in dirs:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise UtCoverError(f"Cannot find project root inside zip: {zip_path}")


def _overlay_tree(source: Path, target: Path) -> None:
    for item in source.iterdir():
        if item.name in EXCLUDED_OVERLAY_NAMES:
            continue
        destination = target / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def _pip_install(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(root)],
        text=True,
        capture_output=True,
    )


def _completed_process_to_dict(process: subprocess.CompletedProcess[str] | None) -> dict[str, Any] | None:
    if process is None:
        return None
    return {
        "returncode": process.returncode,
        "stdout": process.stdout[-4000:],
        "stderr": process.stderr[-4000:],
    }


def _ensure_possible_parent_src(reference_install_dir: str | Path | None) -> None:
    candidates: list[Path] = []
    if reference_install_dir:
        root = Path(reference_install_dir).resolve()
        candidates.extend([root / "src", root.parent / "src", root.parent.parent / "src"])
    candidates.extend([current_tool_root().parent / "src", current_tool_root().parent.parent / "src"])
    for candidate in candidates:
        if (candidate / "ai_ssh_mcp").exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _infer_ai_ssh_mcp_root(reference_install_dir: str | Path | None) -> Path | None:
    info = detect_ai_ssh_mcp(reference_install_dir)
    install_dir = info.get("install_dir")
    if install_dir:
        return Path(install_dir).resolve()
    if reference_install_dir:
        candidate = Path(reference_install_dir).resolve().parent
        if (candidate / "src" / "ai_ssh_mcp").exists():
            return candidate
    return None


def _package_project_root(module_file: Path) -> Path | None:
    for parent in module_file.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def _version_gte(version: str | None, minimum: str) -> bool:
    if not version or version in {"missing", "unknown", "unreadable"}:
        return False
    return _version_tuple(version) >= _version_tuple(minimum)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw in value.split("."):
        digits = "".join(ch for ch in raw if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)
