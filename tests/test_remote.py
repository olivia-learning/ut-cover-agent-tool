import tempfile
import unittest
from pathlib import Path

from ut_cover_agent_tool.config import load_config
from ut_cover_agent_tool.errors import UtCoverError
from ut_cover_agent_tool.remote import (
    RemoteCommandResult,
    diagnose_remote_failure,
    remote_workspace_for,
    run_remote_commands,
    should_sync,
    sync_workspace,
    validate_remote_workspace,
)


class FakeBackend:
    def __init__(self):
        self.cleaned = []
        self.created = []
        self.uploaded = []
        self.results = []

    def mkdir(self, remote_path):
        self.created.append(remote_path)

    def clean_dir(self, remote_path):
        self.cleaned.append(remote_path)

    def upload_file(self, local_path, remote_path):
        self.uploaded.append((Path(local_path).name, remote_path))

    def run(self, command, cwd, timeout=None):
        self.results.append((command, cwd, timeout))
        if "build" in command:
            return RemoteCommandResult(command, 0, "build ok")
        return RemoteCommandResult(command, 0, "dt ok")

    def download_file(self, remote_path, local_path):
        return False

    def close(self):
        pass


class RemoteTests(unittest.TestCase):
    def test_default_sync_pattern_includes_root_files_and_excludes_build_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover.yaml").write_text(
                "\n".join(
                    [
                        'execution_mode: "remote"',
                        'remote_workspace_root: "/tmp/ut-cover"',
                        'sync_include: ["**/*"]',
                        'sync_exclude: ["build/**", ".git/**"]',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(repo)

        self.assertTrue(should_sync("CMakeLists.txt", config))
        self.assertTrue(should_sync("src/app.cpp", config))
        self.assertFalse(should_sync("build/app.o", config))
        self.assertFalse(should_sync(".git/config", config))

    def test_sync_workspace_uploads_uncommitted_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
            (repo / "tests").mkdir()
            (repo / "tests" / "test_app.cpp").write_text("TEST(App, Works) {}\n", encoding="utf-8")
            (repo / "build").mkdir()
            (repo / "build" / "app.o").write_text("ignored\n", encoding="utf-8")
            (repo / ".ut-cover.yaml").write_text(
                "\n".join(
                    [
                        'execution_mode: "remote"',
                        'remote_workspace_root: "/tmp/ut-cover"',
                        'sync_include: ["**/*"]',
                        'sync_exclude: ["build/**", ".ut-cover/**"]',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(repo)
            backend = FakeBackend()

            result = sync_workspace(repo, config, backend, run_id="run-1")

        self.assertTrue(result["ok"])
        self.assertIn("CMakeLists.txt", result["uploaded_files"])
        self.assertIn("tests/test_app.cpp", result["uploaded_files"])
        self.assertNotIn("build/app.o", result["uploaded_files"])
        self.assertEqual(backend.cleaned, [result["remote_workspace"]])

    def test_remote_workspace_path_safety(self):
        with self.assertRaises(UtCoverError):
            validate_remote_workspace("/tmp")
        with self.assertRaises(UtCoverError):
            validate_remote_workspace("relative/path")
        with self.assertRaises(UtCoverError):
            validate_remote_workspace("/tmp/ut-cover/../bad")

    def test_remote_workspace_for_sanitizes_repo_name(self):
        with tempfile.TemporaryDirectory(prefix="repo with space ") as tmp:
            repo = Path(tmp)
            config = load_config(repo)
            path = remote_workspace_for(repo, config, "run-1")

        self.assertTrue(path.startswith("/tmp/ut-cover/"))
        self.assertNotIn(" ", path)
        self.assertTrue(path.endswith("/run-1"))

    def test_run_remote_commands_returns_next_action_on_dt_failure(self):
        class FailingDtBackend(FakeBackend):
            def run(self, command, cwd, timeout=None):
                if "dt" in command:
                    return RemoteCommandResult(command, 9, "dt failed")
                return RemoteCommandResult(command, 0, "build ok")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover.yaml").write_text(
                "\n".join(
                    [
                        'remote_build_command: "build.sh"',
                        'remote_dt_command: "dt.sh"',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(repo)

        result = run_remote_commands(config, FailingDtBackend(), "/tmp/ut-cover/repo/run-1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["next_action"], "remote_diagnose")

        diagnosis = diagnose_remote_failure(result)
        self.assertEqual(diagnosis["category"], "dt_failure")
        self.assertEqual(diagnosis["next_action"], "fix_test_code")

    def test_diagnose_remote_environment_failure_asks_user(self):
        result = {
            "build_result": {
                "ok": False,
                "stdout": "",
                "stderr": "cmake: command not found",
            },
            "dt_result": None,
        }

        diagnosis = diagnose_remote_failure(result)

        self.assertFalse(diagnosis["ok"])
        self.assertEqual(diagnosis["category"], "environment_or_path")
        self.assertEqual(diagnosis["next_action"], "ask_user_environment")

    def test_autonomous_environment_failure_runs_recovery_commands_and_retries(self):
        class RecoveringBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.build_attempts = 0

            def run(self, command, cwd, timeout=None):
                self.results.append((command, cwd, timeout))
                if command == "source /opt/env.sh":
                    return RemoteCommandResult(command, 0, "env fixed")
                if "build" in command:
                    self.build_attempts += 1
                    if self.build_attempts == 1:
                        return RemoteCommandResult(command, 127, "", "cmake: command not found")
                    return RemoteCommandResult(command, 0, "build ok")
                return RemoteCommandResult(command, 0, "dt ok")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover.yaml").write_text(
                "\n".join(
                    [
                        "interaction_mode: autonomous",
                        "autonomous_recovery_commands:",
                        "  - source /opt/env.sh",
                        "autonomous_max_iterations: 2",
                        'remote_build_command: "build.sh"',
                        'remote_dt_command: "dt.sh"',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(repo)
            backend = RecoveringBackend()

            result = run_remote_commands(config, backend, "/tmp/ut-cover/repo/run-1")

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["recovery_results"][0]["command"], "source /opt/env.sh")

    def test_autonomous_environment_failure_without_recovery_archives_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".ut-cover.yaml").write_text("interaction_mode: autonomous\n", encoding="utf-8")
            config = load_config(repo)
        result = {
            "build_result": {
                "ok": False,
                "stdout": "",
                "stderr": "cmake: command not found",
            },
            "dt_result": None,
        }

        diagnosis = diagnose_remote_failure(result, config=config)

        self.assertEqual(diagnosis["category"], "environment_or_path")
        self.assertEqual(diagnosis["next_action"], "archive_issue")


if __name__ == "__main__":
    unittest.main()
