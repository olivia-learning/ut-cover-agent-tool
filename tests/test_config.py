import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.config import load_config


class ConfigTests(unittest.TestCase):
    def test_defaults_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(tmp)
        self.assertEqual(config.coverage_report, "coverage.json")
        self.assertEqual(config.source_dirs, ["src"])
        self.assertIsNone(config.coverage_threshold)
        self.assertEqual(config.execution_mode, "local")
        self.assertEqual(config.remote_backend, "ai_ssh_mcp")
        self.assertEqual(config.remote_workspace_root, "/tmp/ut-cover")
        self.assertIsNone(config.config_path)

    def test_load_yaml_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".ut-cover.yaml"
            path.write_text(
                "\n".join(
                    [
                        'test_command: "python -m unittest"',
                        'coverage_report: "cov.xml"',
                        "source_dirs:",
                        "  - app",
                        "test_dirs: [specs]",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(tmp)
        self.assertEqual(config.test_command, "python -m unittest")
        self.assertEqual(config.coverage_report, "cov.xml")
        self.assertEqual(config.source_dirs, ["app"])
        self.assertEqual(config.test_dirs, ["specs"])

    def test_load_coverage_and_remote_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".ut-cover.yaml"
            path.write_text(
                "\n".join(
                    [
                        "coverage_threshold: 80",
                        "changed_files_coverage_threshold: 85",
                        "coverage_unknown_action: fail",
                        "execution_mode: remote",
                        "remote_build_command: ./build.sh",
                        "remote_dt_command: ./run_dt.sh",
                        "remote_artifacts:",
                        "  - out/coverage.xml",
                        "sync_include:",
                        "  - src/**",
                        "sync_exclude:",
                        "  - build/**",
                        "remote_clean_before_sync: false",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(tmp)
        self.assertEqual(config.coverage_threshold, 80.0)
        self.assertEqual(config.changed_files_coverage_threshold, 85.0)
        self.assertEqual(config.coverage_unknown_action, "fail")
        self.assertEqual(config.execution_mode, "remote")
        self.assertEqual(config.remote_build_command, "./build.sh")
        self.assertEqual(config.remote_dt_command, "./run_dt.sh")
        self.assertEqual(config.remote_artifacts, ["out/coverage.xml"])
        self.assertEqual(config.sync_include, ["src/**"])
        self.assertEqual(config.sync_exclude, ["build/**"])
        self.assertFalse(config.remote_clean_before_sync)


if __name__ == "__main__":
    unittest.main()
