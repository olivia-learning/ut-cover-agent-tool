import json
import sys
import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.cli import main


class CliFlowTests(unittest.TestCase):
    def test_run_coverage_and_report_with_fake_coverage_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            writer = repo / "write_coverage.py"
            writer.write_text(
                "import json\n"
                "open('coverage.json', 'w', encoding='utf-8').write(json.dumps({\n"
                "  'totals': {'covered_lines': 1, 'missing_lines': 1, 'num_statements': 2, 'percent_covered': 50.0},\n"
                "  'files': {'src/app.py': {'summary': {'covered_lines': 1, 'missing_lines': 1, 'num_statements': 2, 'percent_covered': 50.0}, 'missing_lines': [2]}}\n"
                "}))\n",
                encoding="utf-8",
            )
            config = repo / ".ut-cover.yaml"
            command = f"{sys.executable} write_coverage.py".replace("'", "''")
            config.write_text(
                "\n".join(
                    [
                        f"coverage_command: '{command}'",
                        'coverage_report: "coverage.json"',
                    ]
                ),
                encoding="utf-8",
            )

            run_code = main(["run-coverage", "--repo", str(repo), "--output", ".ut-cover/coverage.json"])
            report_code = main(
                [
                    "report",
                    "--analysis",
                    str(repo / "missing-analysis.json"),
                    "--coverage",
                    str(repo / ".ut-cover" / "coverage.json"),
                    "--output",
                    str(repo / ".ut-cover" / "report.md"),
                    "--json-output",
                    str(repo / ".ut-cover" / "report.json"),
                    "--touched-test",
                    "tests/test_app.py",
                ]
            )

            self.assertEqual(run_code, 0)
            self.assertEqual(report_code, 0)
            payload = json.loads((repo / ".ut-cover" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["coverage"]["percent"], 50.0)
            self.assertEqual(payload["touched_tests"], ["tests/test_app.py"])


if __name__ == "__main__":
    unittest.main()
