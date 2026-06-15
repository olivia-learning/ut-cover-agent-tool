from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap upgrade from a newly extracted ut-cover-agent-tool ZIP.")
    parser.add_argument("--install-dir", required=True, help="Existing ut-cover-agent-tool install directory.")
    parser.add_argument("--ut-zip", help="Original ut-cover-agent-tool.zip path. Defaults to this script's package root.")
    parser.add_argument("--skip-pip-install", action="store_true", help="Skip pip install, mainly for tests.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "src"))
    from ut_cover_agent_tool.upgrade import upgrade_from_zip

    ut_zip = Path(args.ut_zip).resolve() if args.ut_zip else _make_temp_zip_hint(project_root)
    result = upgrade_from_zip(args.install_dir, ut_zip, run_pip_install=not args.skip_pip_install)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _make_temp_zip_hint(project_root: Path) -> Path:
    # The normal path passes --ut-zip. This fallback lets the error message name the expected package.
    return project_root.parent / "ut-cover-agent-tool.zip"


if __name__ == "__main__":
    raise SystemExit(main())
