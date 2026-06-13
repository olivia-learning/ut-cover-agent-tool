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


if __name__ == "__main__":
    unittest.main()
