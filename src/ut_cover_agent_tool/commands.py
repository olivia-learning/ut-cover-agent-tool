from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }


def run_shell(command: str, cwd: str | Path = ".", timeout: int | None = None) -> CommandResult:
    import time

    cwd_path = Path(cwd).resolve()
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(cwd_path),
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    return CommandResult(
        command=command,
        cwd=str(cwd_path),
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )
