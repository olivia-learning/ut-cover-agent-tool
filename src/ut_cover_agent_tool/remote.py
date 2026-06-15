from __future__ import annotations

import fnmatch
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .config import ToolConfig
from .errors import UtCoverError


@dataclass(frozen=True)
class RemoteCommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }


class RemoteBackend(Protocol):
    def mkdir(self, remote_path: str) -> None: ...
    def clean_dir(self, remote_path: str) -> None: ...
    def upload_file(self, local_path: Path, remote_path: str) -> None: ...
    def run(self, command: str, cwd: str, timeout: int | None = None) -> RemoteCommandResult: ...
    def download_file(self, remote_path: str, local_path: Path) -> bool: ...
    def close(self) -> None: ...


class AiSshMcpRemoteBackend:
    """Remote backend that reuses the sibling ai_ssh_mcp connection and keyring config."""

    def __init__(self) -> None:
        _ensure_ai_ssh_mcp_importable()
        try:
            from ai_ssh_mcp.config import load_config
            from ai_ssh_mcp.credentials import CredentialStore
            from ai_ssh_mcp.ssh_client import EmbeddedSSHSession
        except ImportError as exc:
            raise UtCoverError(
                "ai_ssh_mcp is not importable. Install/configure the Create_tool SSH MCP service first."
            ) from exc

        config = load_config()
        secrets = CredentialStore().get_device_secrets(config)
        self._session = EmbeddedSSHSession(config, secrets)
        self._session.connect()
        self._sftp = self._session._require_client().open_sftp()

    def mkdir(self, remote_path: str) -> None:
        self._run_shell(f"mkdir -p {shell_quote(remote_path)}", timeout=30)

    def clean_dir(self, remote_path: str) -> None:
        validate_remote_workspace(remote_path)
        self._run_shell(f"rm -rf {shell_quote(remote_path)} && mkdir -p {shell_quote(remote_path)}", timeout=120)

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        parent = str(PurePosixPath(remote_path).parent)
        self.mkdir(parent)
        self._sftp.put(str(local_path), remote_path)

    def run(self, command: str, cwd: str, timeout: int | None = None) -> RemoteCommandResult:
        validate_remote_workspace(cwd)
        started = time.monotonic()
        wrapped = f"cd {shell_quote(cwd)} && {command}"
        result = self._run_shell(wrapped, timeout=timeout or 3600)
        return RemoteCommandResult(
            command=command,
            exit_code=result.exit_status,
            stdout=result.stdout,
            stderr=getattr(result, "stderr", ""),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def download_file(self, remote_path: str, local_path: Path) -> bool:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self._sftp.get(remote_path, str(local_path))
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._session.close()

    def _run_shell(self, command: str, timeout: int):
        return self._session._run_shell_command(command=command, purpose="ut-cover remote execution", timeout=timeout)


def create_remote_backend(config: ToolConfig) -> RemoteBackend:
    if config.remote_backend != "ai_ssh_mcp":
        raise UtCoverError(f"Unsupported remote_backend: {config.remote_backend}")
    return AiSshMcpRemoteBackend()


def ai_ssh_mcp_available() -> bool:
    try:
        _ensure_ai_ssh_mcp_importable()
        import ai_ssh_mcp  # noqa: F401
    except Exception:
        return False
    return True


def _ensure_ai_ssh_mcp_importable() -> None:
    try:
        import ai_ssh_mcp  # noqa: F401
        return
    except ImportError:
        pass

    current = Path(__file__).resolve()
    candidates = [
        current.parents[3] / "src",
        current.parents[2].parent / "src",
    ]
    for candidate in candidates:
        if (candidate / "ai_ssh_mcp").exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            try:
                import ai_ssh_mcp  # noqa: F401
                return
            except ImportError:
                continue


def make_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def remote_workspace_for(repo: str | Path, config: ToolConfig, run_id: str) -> str:
    root = config.remote_workspace_root.rstrip("/")
    repo_name = safe_repo_name(Path(repo).resolve().name)
    workspace = f"{root}/{repo_name}/{run_id}"
    validate_remote_workspace(workspace)
    return workspace


def safe_repo_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value).strip("._")
    if not safe:
        raise UtCoverError("Repository name is not usable for a remote workspace.")
    return safe


def validate_remote_workspace(remote_path: str) -> None:
    normalized = remote_path.replace("\\", "/")
    if not normalized.startswith("/"):
        raise UtCoverError("remote workspace must be an absolute Linux path")
    parts = [part for part in normalized.split("/") if part]
    if ".." in parts or len(parts) < 3:
        raise UtCoverError(f"unsafe remote workspace: {remote_path}")
    blocked = {"/", "/tmp", "/home", "/root", "/var", "/usr", "/opt"}
    if normalized.rstrip("/") in blocked:
        raise UtCoverError(f"remote workspace is too broad: {remote_path}")


def collect_sync_files(repo: str | Path, config: ToolConfig) -> list[Path]:
    repo_path = Path(repo).resolve()
    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = normalize_rel(path.relative_to(repo_path))
        if should_sync(rel, config):
            files.append(path)
    return files


def should_sync(relative_path: str, config: ToolConfig) -> bool:
    rel = normalize_rel(relative_path)
    included = any(_matches_sync_pattern(rel, pattern) for pattern in config.sync_include)
    excluded = any(fnmatch.fnmatch(rel, normalize_rel(pattern)) for pattern in config.sync_exclude)
    return included and not excluded


def _matches_sync_pattern(relative_path: str, pattern: str) -> bool:
    normalized = normalize_rel(pattern)
    if normalized in {"**", "**/*", "*"}:
        return True
    return fnmatch.fnmatch(relative_path, normalized)


def sync_workspace(repo: str | Path, config: ToolConfig, backend: RemoteBackend, run_id: str | None = None) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    current_run_id = run_id or make_run_id()
    workspace = remote_workspace_for(repo_path, config, current_run_id)
    if config.remote_clean_before_sync:
        backend.clean_dir(workspace)
    else:
        backend.mkdir(workspace)

    files = collect_sync_files(repo_path, config)
    uploaded: list[str] = []
    for local_path in files:
        rel = normalize_rel(local_path.relative_to(repo_path))
        remote_path = str(PurePosixPath(workspace) / rel)
        backend.upload_file(local_path, remote_path)
        uploaded.append(rel)
    return {
        "ok": True,
        "run_id": current_run_id,
        "remote_workspace": workspace,
        "uploaded_count": len(uploaded),
        "uploaded_files": uploaded,
        "next_action": "continue",
    }


def run_remote_commands(config: ToolConfig, backend: RemoteBackend, remote_workspace: str, timeout: int | None = None) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    recovery_results: list[dict[str, Any]] = []
    max_attempts = config.autonomous_max_iterations if config.interaction_mode == "autonomous" else 1
    max_attempts = max(1, max_attempts)

    for attempt in range(1, max_attempts + 1):
        result = _run_build_dt_once(config, backend, remote_workspace, timeout=timeout)
        result["attempt"] = attempt
        attempts.append(result)
        if result["ok"]:
            result["attempts"] = attempts
            result["recovery_results"] = recovery_results
            return result

        diagnosis = diagnose_remote_failure(result, config=config)
        result["diagnosis"] = diagnosis
        should_recover = (
            config.interaction_mode == "autonomous"
            and diagnosis.get("next_action") == "run_recovery_commands"
            and bool(config.autonomous_recovery_commands)
            and attempt < max_attempts
        )
        if not should_recover:
            result["attempts"] = attempts
            result["recovery_results"] = recovery_results
            return result

        for command in config.autonomous_recovery_commands:
            recovery = backend.run(command, cwd=remote_workspace, timeout=timeout)
            recovery_results.append(recovery.to_dict())

    final = attempts[-1]
    final["attempts"] = attempts
    final["recovery_results"] = recovery_results
    return final


def _run_build_dt_once(config: ToolConfig, backend: RemoteBackend, remote_workspace: str, timeout: int | None = None) -> dict[str, Any]:
    build_result = None
    dt_result = None
    ok = True
    next_action = "continue"

    if config.remote_build_command:
        build_result = backend.run(config.remote_build_command, cwd=remote_workspace, timeout=timeout)
        ok = build_result.ok
        if not ok:
            next_action = "remote_diagnose"
    if ok and config.remote_dt_command:
        dt_result = backend.run(config.remote_dt_command, cwd=remote_workspace, timeout=timeout)
        ok = dt_result.ok
        if not ok:
            next_action = "remote_diagnose"

    return {
        "ok": ok,
        "remote_workspace": remote_workspace,
        "build_result": build_result.to_dict() if build_result else None,
        "dt_result": dt_result.to_dict() if dt_result else None,
        "next_action": next_action,
    }


def fetch_remote_artifacts(
    repo: str | Path,
    config: ToolConfig,
    backend: RemoteBackend,
    remote_workspace: str,
    output_dir: str | Path = ".ut-cover/remote",
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    local_root = (repo_path / output_dir).resolve()
    fetched: list[dict[str, Any]] = []
    for artifact in config.remote_artifacts:
        remote_path = str(PurePosixPath(remote_workspace) / artifact)
        local_path = local_root / artifact.replace("/", "_")
        ok = backend.download_file(remote_path, local_path)
        fetched.append(
            {
                "remote_path": remote_path,
                "local_path": str(local_path),
                "ok": ok,
            }
        )
    return {
        "ok": any(item["ok"] for item in fetched),
        "remote_workspace": remote_workspace,
        "fetched": fetched,
        "next_action": "continue",
    }


def diagnose_remote_failure(
    remote_result: dict[str, Any],
    fetched_text: str = "",
    config: ToolConfig | None = None,
) -> dict[str, Any]:
    build = remote_result.get("build_result") or {}
    dt = remote_result.get("dt_result") or {}
    text = "\n".join(
        [
            str(build.get("stdout", "")),
            str(build.get("stderr", "")),
            str(dt.get("stdout", "")),
            str(dt.get("stderr", "")),
            fetched_text,
        ]
    ).lower()

    if any(token in text for token in ["command not found", "not found", "no such file or directory", "permission denied"]):
        category = "environment_or_path"
        next_action = "ask_user_environment"
    elif any(token in text for token in ["undefined reference", "fatal error:", "compilation terminated", "error:"]):
        if any(token in text for token in ["test", "_test", "gtest", "pytest", "jest"]):
            category = "test_code_compile_error"
            next_action = "fix_test_code"
        else:
            category = "source_compile_error"
            next_action = "stop"
    elif dt and dt.get("ok") is False:
        category = "dt_failure"
        next_action = "fix_test_code"
    else:
        category = "unknown"
        next_action = "stop"

    if config and config.interaction_mode == "autonomous":
        if category == "environment_or_path":
            next_action = "run_recovery_commands" if config.autonomous_recovery_commands else "archive_issue"
        elif category in {"source_compile_error", "unknown"}:
            next_action = "archive_issue"

    return {
        "ok": category not in {"environment_or_path", "source_compile_error", "unknown"},
        "category": category,
        "next_action": next_action,
        "message": _diagnosis_message(category),
    }


def normalize_rel(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _diagnosis_message(category: str) -> str:
    return {
        "environment_or_path": "Remote environment or path looks wrong; ask the user to fix the executor.",
        "test_code_compile_error": "The test code appears to cause compilation failure; the AI may fix tests.",
        "source_compile_error": "Production/source code compilation failed; stop unless the user asks to fix source.",
        "dt_failure": "DT command failed; inspect logs and fix tests only when clearly caused by test code.",
        "unknown": "Remote failure could not be classified safely.",
    }[category]
