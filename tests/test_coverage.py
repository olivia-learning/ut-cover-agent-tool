import json
import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.coverage import parse_cobertura_xml, parse_coverage_json


class CoverageTests(unittest.TestCase):
    def test_parse_coverage_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coverage.json"
            path.write_text(
                json.dumps(
                    {
                        "totals": {
                            "covered_lines": 8,
                            "missing_lines": 2,
                            "num_statements": 10,
                            "percent_covered": 80.0,
                        },
                        "files": {
                            "src/app.py": {
                                "summary": {
                                    "covered_lines": 8,
                                    "missing_lines": 2,
                                    "num_statements": 10,
                                    "percent_covered": 80.0,
                                },
                                "missing_lines": [4, 9],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            summary = parse_coverage_json(path)
        self.assertEqual(summary.percent, 80.0)
        self.assertEqual(summary.files[0].missing_lines, [4, 9])

    def test_parse_cobertura_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coverage.xml"
            path.write_text(
                """<?xml version="1.0" ?>
<coverage line-rate="0.5" lines-covered="1" lines-valid="2">
  <packages>
    <package>
      <classes>
        <class filename="src/app.py">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
                encoding="utf-8",
            )
            summary = parse_cobertura_xml(path)
        self.assertEqual(summary.percent, 50.0)
        self.assertEqual(summary.files[0].missing_lines, [2])


if __name__ == "__main__":
    unittest.main()
