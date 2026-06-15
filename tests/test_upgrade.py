import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ut_cover_agent_tool.upgrade import build_upgrade_status, read_zip_info, upgrade_from_zip


def make_tool_zip(path: Path, version: str = "9.9.9") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ut-cover-agent-tool/VERSION", version)
        archive.writestr("ut-cover-agent-tool/pyproject.toml", "[project]\nname='ut-cover-agent-tool'\n")
        archive.writestr("ut-cover-agent-tool/README.md", "new readme\n")
        archive.writestr(
            "ut-cover-agent-tool/ZIP_MANIFEST.json",
            json.dumps({"tool": "ut-cover-agent-tool", "version": version}),
        )
    return path


class UpgradeTests(unittest.TestCase):
    def test_read_zip_info_uses_manifest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = make_tool_zip(Path(tmp) / "ut-cover-agent-tool.zip", "2.0.0")

            info = read_zip_info(zip_path, "ut-cover-agent-tool")

        self.assertTrue(info["exists"])
        self.assertEqual(info["version"], "2.0.0")
        self.assertEqual(info["tool"], "ut-cover-agent-tool")

    def test_upgrade_from_zip_overlays_tool_but_preserves_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ut-cover-agent-tool"
            root.mkdir()
            (root / "VERSION").write_text("1.0.0", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "keep.txt").write_text("keep", encoding="utf-8")
            zip_path = make_tool_zip(Path(tmp) / "ut-cover-agent-tool.zip", "2.0.0")

            result = upgrade_from_zip(root, zip_path, run_pip_install=False)

            self.assertTrue(result["ok"])
            self.assertEqual((root / "VERSION").read_text(encoding="utf-8"), "2.0.0")
            self.assertTrue((root / ".venv" / "keep.txt").exists())
            self.assertTrue(Path(result["backup_dir"]).exists())
            self.assertTrue((root / ".ut-cover-upgrade" / "upgrade-report.json").exists())

    def test_upgrade_status_reports_zip_and_current_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ut-cover-agent-tool"
            root.mkdir()
            (root / "VERSION").write_text("1.0.0", encoding="utf-8")
            zip_path = make_tool_zip(Path(tmp) / "ut-cover-agent-tool.zip", "2.0.0")

            status = build_upgrade_status(install_dir=root, ut_zip=zip_path, zip_dir=tmp)

            self.assertEqual(status["install_dir"], str(root.resolve()))
            self.assertEqual(status["ut_zip"]["version"], "2.0.0")
            self.assertIn("next_action", status)


if __name__ == "__main__":
    unittest.main()
