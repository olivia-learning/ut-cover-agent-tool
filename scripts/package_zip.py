from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


EXCLUDED_DIRS = {
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
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ut-cover-agent-tool.zip")
    parser.add_argument("--output", default="../ut-cover-agent-tool.zip", help="Output zip path.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output = (project_root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_root.rglob("*")):
            if path == output or should_exclude(path, project_root):
                continue
            archive.write(path, path.relative_to(project_root.parent))

    print(f"Wrote {output}")
    return 0


def should_exclude(path: Path, project_root: Path) -> bool:
    rel = path.relative_to(project_root)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    if path.is_dir():
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name.endswith(".egg-info"):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
