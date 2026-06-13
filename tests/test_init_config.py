import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.cli import main
from ut_cover_agent_tool.presets import detect_preset


class InitConfigTests(unittest.TestCase):
    def test_init_config_writes_beginner_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            code = main(["init-config", "--repo", str(repo), "--preset", "python-unittest"])
            config = repo / ".ut-cover.yaml"
            self.assertEqual(code, 0)
            self.assertTrue(config.exists())
            text = config.read_text(encoding="utf-8")
            self.assertIn("python -m unittest discover", text)
            self.assertIn("coverage.json", text)

    def test_init_config_does_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            config = repo / ".ut-cover.yaml"
            config.write_text("test_command: 'keep'\n", encoding="utf-8")

            code = main(["init-config", "--repo", str(repo)])

            self.assertEqual(code, 2)
            self.assertEqual(config.read_text(encoding="utf-8"), "test_command: 'keep'\n")

    def test_init_config_allows_command_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            code = main(
                [
                    "init-config",
                    "--repo",
                    str(repo),
                    "--preset",
                    "python-pytest",
                    "--coverage-command",
                    "custom coverage",
                ]
            )
            text = (repo / ".ut-cover.yaml").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("custom coverage", text)

    def test_auto_detects_cpp_cmake_and_writes_gcovr_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "CMakeLists.txt").write_text("project(example)\n", encoding="utf-8")
            code = main(["init-config", "--repo", str(repo)])
            text = (repo / ".ut-cover.yaml").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("preset: cpp-cmake-gcovr", text)
        self.assertIn("ctest --test-dir build --output-on-failure", text)
        self.assertIn("gcovr -r . --xml-pretty -o coverage.xml", text)

    def test_detect_preset_for_common_repo_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "package.json").write_text(
                '{"scripts":{"test":"jest"},"devDependencies":{"jest":"latest"}}',
                encoding="utf-8",
            )
            self.assertEqual(detect_preset(repo), "node-jest")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text('[tool.pytest.ini_options]\n', encoding="utf-8")
            self.assertEqual(detect_preset(repo), "python-pytest")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
            self.assertEqual(detect_preset(repo), "cpp-cmake-gcovr")


if __name__ == "__main__":
    unittest.main()
