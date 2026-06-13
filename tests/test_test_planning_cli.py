import json
import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.cli import main


class TestPlanningCliTests(unittest.TestCase):
    def test_plan_tests_and_review_tests_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover").mkdir()
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            (repo / "src" / "math.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
            (repo / "tests" / "test_math.py").write_text(
                "from src.math import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                encoding="utf-8",
            )
            (repo / ".ut-cover" / "analysis.json").write_text(
                json.dumps({"commits": [{"changed_files": [{"path": "src/math.py", "status": "M"}]}]}),
                encoding="utf-8",
            )

            plan_code = main(["plan-tests", "--repo", str(repo)])
            review_code = main(["review-tests", "--repo", str(repo), "--touched-test", "tests/test_math.py"])
            plan = json.loads((repo / ".ut-cover" / "test-plan.json").read_text(encoding="utf-8"))
            review = json.loads((repo / ".ut-cover" / "test-review.json").read_text(encoding="utf-8"))

        self.assertEqual(plan_code, 0)
        self.assertEqual(review_code, 0)
        self.assertEqual(plan["entries"][0]["status"], "ready")
        self.assertTrue(review["ok"])


if __name__ == "__main__":
    unittest.main()
