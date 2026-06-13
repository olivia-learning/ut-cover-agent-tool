from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .errors import ToolUnavailableError, UtCoverError


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    previous_path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "status": self.status,
            "previous_path": self.previous_path,
        }


@dataclass(frozen=True)
class CommitAnalysis:
    commit: str
    parents: list[str]
    author_name: str
    author_email: str
    author_date: str
    subject: str
    changed_files: list[ChangedFile]
    diff: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "parents": self.parents,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_date": self.author_date,
            "subject": self.subject,
            "changed_files": [item.to_dict() for item in self.changed_files],
            "diff": self.diff,
        }


GIT_ENV_VAR = "UT_COVER_GIT"


def ensure_git_available() -> str:
    git = resolve_git_executable()
    if git is None:
        raise ToolUnavailableError(
            "git is not available. Install Git, add git.exe to PATH, or set UT_COVER_GIT to the full git.exe path."
        )
    return git


def resolve_git_executable() -> str | None:
    from_path = shutil.which("git")
    if from_path:
        return from_path

    configured = os.environ.get(GIT_ENV_VAR)
    if configured and _is_git_executable(configured):
        return str(Path(configured).resolve())

    for candidate in _windows_git_candidates():
        if _is_git_executable(candidate):
            return str(Path(candidate).resolve())
    return None


def _windows_git_candidates() -> list[Path]:
    candidates = [
        Path(r"C:\Program Files\Git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\bin\git.exe"),
        Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\git.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    user_profile = os.environ.get("USERPROFILE")
    program_data = os.environ.get("ProgramData")
    if local_app_data:
        local = Path(local_app_data)
        candidates.extend(
            [
                local / "Programs" / "Git" / "cmd" / "git.exe",
                local / "Programs" / "Git" / "bin" / "git.exe",
            ]
        )
        github_desktop = local / "GitHubDesktop"
        if github_desktop.exists():
            candidates.extend(
                sorted(github_desktop.glob("app-*/resources/app/git/cmd/git.exe"), reverse=True)
            )
            candidates.extend(
                sorted(github_desktop.glob("app-*/resources/app/git/mingw64/bin/git.exe"), reverse=True)
            )
    if user_profile:
        profile = Path(user_profile)
        candidates.extend(
            [
                profile / "scoop" / "apps" / "git" / "current" / "cmd" / "git.exe",
                profile / "scoop" / "shims" / "git.exe",
            ]
        )
    if program_data:
        candidates.append(Path(program_data) / "chocolatey" / "bin" / "git.exe")
    return candidates


def _is_git_executable(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.is_file() and candidate.name.lower() == "git.exe"


def ensure_git_repo(repo: str | Path) -> None:
    result = run_git(["rev-parse", "--is-inside-work-tree"], repo)
    if result.strip() != "true":
        raise UtCoverError(f"Not a git repository: {Path(repo).resolve()}")


def parse_commit_inputs(commits: list[str] | None = None, commit_file: str | Path | None = None) -> list[str]:
    values: list[str] = []
    for item in commits or []:
        values.extend(_split_commit_text(item))
    if commit_file:
        values.extend(_split_commit_text(Path(commit_file).read_text(encoding="utf-8")))
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def analyze_commits(repo: str | Path, commits: list[str]) -> list[CommitAnalysis]:
    ensure_git_available()
    ensure_git_repo(repo)
    return [analyze_commit(repo, commit) for commit in commits]


def analyze_commit(repo: str | Path, commit: str) -> CommitAnalysis:
    metadata = run_git(["log", "-1", "--pretty=format:%H%n%P%n%an%n%ae%n%aI%n%s", commit], repo)
    lines = metadata.splitlines()
    if len(lines) < 6:
        raise UtCoverError(f"Unable to read commit metadata for {commit}")
    canonical, parents, author_name, author_email, author_date = lines[:5]
    subject = "\n".join(lines[5:]).strip()
    changed_files = parse_name_status(
        run_git(["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "-M", commit], repo)
    )
    diff = run_git(["show", "--format=", "--no-ext-diff", "--find-renames", "--unified=80", commit], repo)
    return CommitAnalysis(
        commit=canonical,
        parents=[item for item in parents.split(" ") if item],
        author_name=author_name,
        author_email=author_email,
        author_date=author_date,
        subject=subject,
        changed_files=changed_files,
        diff=diff,
    )


def parse_name_status(raw: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            files.append(ChangedFile(path=parts[2], status=status, previous_path=parts[1]))
        elif len(parts) >= 2:
            files.append(ChangedFile(path=parts[1], status=status))
    return files


def run_git(args: list[str], repo: str | Path) -> str:
    git = ensure_git_available()
    completed = subprocess.run(
        [git, *args],
        cwd=str(Path(repo).resolve()),
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise UtCoverError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout


def _split_commit_text(text: str) -> list[str]:
    values: list[str] = []
    for line in text.replace(",", "\n").splitlines():
        item = line.split("#", 1)[0].strip()
        if not item:
            continue
        values.extend(part for part in item.split() if part)
    return values
