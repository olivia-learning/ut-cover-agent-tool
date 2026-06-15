import tempfile
import unittest
import zipfile
import json
from pathlib import Path


class PackageZipTests(unittest.TestCase):
    def test_packaged_zip_names_are_scoped_to_tool_folder(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ut-cover-agent-tool.zip"
            import subprocess
            import sys

            completed = subprocess.run(
                [sys.executable, str(project_root / "scripts" / "package_zip.py"), "--output", str(output)],
                cwd=str(project_root),
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                manifest = json.loads(archive.read("ut-cover-agent-tool/ZIP_MANIFEST.json").decode("utf-8"))
        self.assertTrue(all(name.startswith("ut-cover-agent-tool/") for name in names))
        self.assertFalse(any(name.startswith("src/ai_ssh_mcp") for name in names))
        self.assertIn("ut-cover-agent-tool/OPENCODE_ZIP_SETUP.md", names)
        self.assertIn("ut-cover-agent-tool/OPENCODE_UPGRADE.md", names)
        self.assertIn("ut-cover-agent-tool/UPGRADE.md", names)
        self.assertIn("ut-cover-agent-tool/REMOTE_WORKFLOW.md", names)
        self.assertIn("ut-cover-agent-tool/.opencode/agents/ut-coverage-writer.md", names)
        self.assertIn("ut-cover-agent-tool/VERSION", names)
        self.assertIn("ut-cover-agent-tool/ZIP_MANIFEST.json", names)
        self.assertEqual(manifest["tool"], "ut-cover-agent-tool")
        self.assertIn("required_ai_ssh_mcp_min_version", manifest)


if __name__ == "__main__":
    unittest.main()
