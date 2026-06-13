import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from ut_cover_agent_tool.errors import ToolUnavailableError
from ut_cover_agent_tool.git_tools import ensure_git_available, parse_commit_inputs, parse_name_status


class GitToolTests(unittest.TestCase):
    def test_parse_commit_inputs_dedupes_and_ignores_comments(self):
        commits = parse_commit_inputs(["abc, def\n# skip\nghi abc"])
        self.assertEqual(commits, ["abc", "def", "ghi"])

    def test_parse_name_status_handles_rename(self):
        parsed = parse_name_status("M\tfile.py\nR100\told.py\tnew.py\n")
        self.assertEqual(parsed[0].path, "file.py")
        self.assertEqual(parsed[1].previous_path, "old.py")
        self.assertEqual(parsed[1].path, "new.py")

    def test_missing_git_has_clear_error(self):
        with patch("shutil.which", return_value=None), patch(
            "ut_cover_agent_tool.git_tools._windows_git_candidates", return_value=[]
        ), patch.dict("os.environ", {"UT_COVER_GIT": ""}):
            with self.assertRaises(ToolUnavailableError) as raised:
                ensure_git_available()
        self.assertIn("git is not available", str(raised.exception))

    def test_can_find_git_from_environment_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = Path(tmp) / "git.exe"
            git.write_text("", encoding="utf-8")
            with patch("shutil.which", return_value=None), patch.dict(
                "os.environ", {"UT_COVER_GIT": str(git)}
            ):
                self.assertEqual(ensure_git_available(), str(git.resolve()))

    def test_can_find_git_from_windows_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = Path(tmp) / "git.exe"
            git.write_text("", encoding="utf-8")
            with patch("shutil.which", return_value=None), patch.dict(
                "os.environ", {"UT_COVER_GIT": ""}
            ), patch("ut_cover_agent_tool.git_tools._windows_git_candidates", return_value=[git]):
                self.assertEqual(ensure_git_available(), str(git.resolve()))


if __name__ == "__main__":
    unittest.main()
