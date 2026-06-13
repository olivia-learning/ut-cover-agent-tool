import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.config import load_config
from ut_cover_agent_tool.test_planning import (
    build_test_plan,
    classify_test_path,
    review_touched_tests,
)


def analysis_for(path: str) -> dict:
    return {
        "commits": [
            {
                "commit": "abc",
                "changed_files": [{"path": path, "status": "M"}],
            }
        ]
    }


class TestPlanningTests(unittest.TestCase):
    def test_prefers_local_unit_neighbor_over_dt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src" / "payment").mkdir(parents=True)
            (repo / "tests" / "payment").mkdir(parents=True)
            (repo / "tests" / "dt").mkdir(parents=True)
            (repo / "src" / "payment" / "charge.py").write_text("def charge(): pass\n", encoding="utf-8")
            (repo / "tests" / "payment" / "test_charge.py").write_text(
                "from src.payment.charge import charge\n\ndef test_charge():\n    assert charge is not None\n",
                encoding="utf-8",
            )
            (repo / "tests" / "dt" / "test_charge_dt.py").write_text(
                "def test_device_charge():\n    assert True\n",
                encoding="utf-8",
            )
            config = load_config(repo)
            plan = build_test_plan(repo, config, analysis_for("src/payment/charge.py"))

        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["recommended_neighbors"][0]["path"], "tests/payment/test_charge.py")
        self.assertEqual(entry["blocked_non_unit_candidates"][0]["path"], "tests/dt/test_charge_dt.py")

    def test_stops_when_only_dt_neighbor_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "tests" / "integration").mkdir(parents=True)
            (repo / "src" / "device.py").write_text("def run(): pass\n", encoding="utf-8")
            (repo / "tests" / "integration" / "test_device.py").write_text(
                "def test_device():\n    assert True\n",
                encoding="utf-8",
            )
            config = load_config(repo)
            plan = build_test_plan(repo, config, analysis_for("src/device.py"))

        entry = plan["entries"][0]
        self.assertEqual(entry["status"], "low_confidence")
        self.assertEqual(entry["recommended_neighbors"], [])
        self.assertEqual(entry["blocked_non_unit_candidates"][0]["classification"], "non_unit")

    def test_include_can_mark_custom_unit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover.yaml").write_text(
                "\n".join(
                    [
                        "test_dirs: [component]",
                        "unit_test_include:",
                        "  - component/dt_unit/test_*.py",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(repo)
            classification, reasons = classify_test_path(config, "component/dt_unit/test_parser.py")

        self.assertEqual(classification, "unit")
        self.assertIn("matched unit_test_include", reasons)

    def test_review_flags_dt_and_missing_assertion(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "tests" / "dt").mkdir(parents=True)
            touched = repo / "tests" / "dt" / "test_device.py"
            touched.write_text("def test_device():\n    run_device()\n", encoding="utf-8")
            config = load_config(repo)
            review = review_touched_tests(repo, config, ["tests/dt/test_device.py"])

        self.assertFalse(review["ok"])
        self.assertIn("non-unit", review["results"][0]["warnings"][0])
        self.assertFalse(review["results"][0]["has_assertion"])


if __name__ == "__main__":
    unittest.main()
