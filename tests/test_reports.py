import unittest

from ut_cover_agent_tool.reports import build_report_payload, render_markdown


class ReportTests(unittest.TestCase):
    def test_markdown_contains_commits_coverage_and_touched_tests(self):
        payload = build_report_payload(
            {
                "commits": [
                    {
                        "commit": "abcdef123456",
                        "subject": "change behavior",
                        "author_name": "A",
                        "author_email": "a@example.com",
                        "author_date": "2026-01-01T00:00:00Z",
                        "changed_files": [{"status": "M", "path": "src/app.py"}],
                    }
                ]
            },
            {
                "test_result": {"ok": True, "command": "test", "exit_code": 0, "duration_ms": 1},
                "coverage": {
                    "format": "coverage-json",
                    "report_path": "coverage.json",
                    "percent": 90.0,
                    "covered_lines": 9,
                    "total_lines": 10,
                    "files": [{"path": "src/app.py", "missing_lines": [10]}],
                },
            },
            ["tests/test_app.py"],
        )
        markdown = render_markdown(payload)
        self.assertIn("abcdef123456", markdown)
        self.assertIn("90.00%", markdown)
        self.assertIn("tests/test_app.py", markdown)
        self.assertIn("src/app.py", markdown)


if __name__ == "__main__":
    unittest.main()
