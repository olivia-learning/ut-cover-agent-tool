import unittest

from ut_cover_agent_tool.config import DEFAULT_CONFIG, ToolConfig
from ut_cover_agent_tool.coverage_gate import evaluate_coverage_gate


def make_config(**overrides):
    data = dict(DEFAULT_CONFIG)
    data.update(overrides)
    return ToolConfig(
        test_command=str(data["test_command"]),
        coverage_command=str(data["coverage_command"]),
        coverage_report=str(data["coverage_report"]),
        source_dirs=list(data["source_dirs"]),
        test_dirs=list(data["test_dirs"]),
        exclude=list(data["exclude"]),
        unit_test_include=list(data["unit_test_include"]),
        unit_test_exclude=list(data["unit_test_exclude"]),
        dt_test_patterns=list(data["dt_test_patterns"]),
        preferred_test_roots=list(data["preferred_test_roots"]),
        coverage_threshold=data["coverage_threshold"],
        changed_files_coverage_threshold=data["changed_files_coverage_threshold"],
        coverage_fail_below_threshold=data["coverage_fail_below_threshold"],
        coverage_unknown_action=data["coverage_unknown_action"],
        execution_mode=str(data["execution_mode"]),
        remote_backend=str(data["remote_backend"]),
        remote_workspace_root=str(data["remote_workspace_root"]),
        remote_build_command=str(data["remote_build_command"]),
        remote_dt_command=str(data["remote_dt_command"]),
        remote_artifacts=list(data["remote_artifacts"]),
        sync_include=list(data["sync_include"]),
        sync_exclude=list(data["sync_exclude"]),
        remote_clean_before_sync=data["remote_clean_before_sync"],
        report_dir=str(data["report_dir"]),
        config_path=None,
    )


class CoverageGateTests(unittest.TestCase):
    def test_gate_passes_when_overall_and_changed_files_meet_goal(self):
        config = make_config(coverage_threshold=80.0, changed_files_coverage_threshold=85.0)
        coverage = {
            "percent": 90.0,
            "files": [{"path": "src/app.py", "percent": 86.0, "missing_lines": []}],
        }
        analysis = {"commits": [{"changed_files": [{"path": "src/app.py"}]}]}

        result = evaluate_coverage_gate(config, coverage, analysis)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["next_action"], "continue")

    def test_gate_fails_changed_file_below_goal(self):
        config = make_config(coverage_threshold=80.0, changed_files_coverage_threshold=85.0)
        coverage = {
            "percent": 90.0,
            "files": [{"path": "src/app.py", "percent": 70.0, "missing_lines": [10, 11]}],
        }
        analysis = {"commits": [{"changed_files": [{"path": "src/app.py"}]}]}

        result = evaluate_coverage_gate(config, coverage, analysis)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["next_action"], "continue_fix_tests")
        self.assertEqual(result["failed_files"][0]["missing_lines"], [10, 11])

    def test_unknown_warn_allows_workflow_to_continue(self):
        config = make_config(coverage_threshold=80.0, coverage_unknown_action="warn")

        result = evaluate_coverage_gate(config, None, None)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["next_action"], "report_unknown_coverage")

    def test_unknown_fail_stops_workflow(self):
        config = make_config(coverage_threshold=80.0, coverage_unknown_action="fail")

        result = evaluate_coverage_gate(config, None, None)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["next_action"], "stop")


if __name__ == "__main__":
    unittest.main()
