"""write_auto_publish_result.py の単体テスト.

仕様: aidlc-docs/plan-work/issue-75.md

実行:

    python -m unittest tests.test_write_auto_publish_result
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "write_auto_publish_result.py"


def run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class WriteAutoPublishResultTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.parent_repo = pathlib.Path(self.tmpdir.name)
        self.result_path = self.parent_repo / ".tmp" / "auto-publish-diary" / "result.json"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _read_result(self) -> dict:
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def test_success_with_worktree_removed(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--draft-url", "https://blog.example.com/entry/2026/05/20/123456",
            "--pr-url", "https://github.com/becky3/article-writer/pull/99",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data, {
            "status": "ok",
            "article_path": "articles/hatena/2026-05-20-diary.md",
            "draft_url": "https://blog.example.com/entry/2026/05/20/123456",
            "pr_url": "https://github.com/becky3/article-writer/pull/99",
            "merged": True,
            "worktree_removed": True,
            "worktree_path": None,
        })

    def test_success_with_worktree_not_removed(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--draft-url", "https://blog.example.com/entry/x",
            "--pr-url", "https://github.com/becky3/article-writer/pull/100",
            "--worktree-removed", "false",
            "--worktree-path", "D:/GitHub/becky3/article-writer-wt-auto-20260520",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["worktree_removed"], False)
        self.assertEqual(data["worktree_path"], "D:/GitHub/becky3/article-writer-wt-auto-20260520")

    def test_error_minimum_fields(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "environment",
            "--error", "親リポに未コミット変更があります",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data, {
            "status": "error",
            "failed_phase": "environment",
            "error": "親リポに未コミット変更があります",
            "article_path": None,
            "draft_url": None,
            "pr_url": None,
            "merged": False,
            "worktree_path": None,
        })

    def test_error_with_partial_progress(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "git",
            "--error", "gh pr merge exit 1",
            "--worktree-path", "D:/wt/x",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--draft-url", "https://blog/x",
            "--pr-url", "https://github.com/.../pull/1",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["failed_phase"], "git")
        self.assertEqual(data["pr_url"], "https://github.com/.../pull/1")
        self.assertEqual(data["merged"], False)

    def test_special_characters_in_values(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--draft-url", "https://blog/entry?a=1&b=\"quoted\"&c=back\\slash&d=$VAR",
            "--pr-url", "https://github.com/.../pull/1",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["draft_url"], "https://blog/entry?a=1&b=\"quoted\"&c=back\\slash&d=$VAR")

    def test_japanese_in_error_message(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "publish",
            "--error", "publish_hatena.py exit 1: 認証エラー（keyring 未登録）",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["error"], "publish_hatena.py exit 1: 認証エラー（keyring 未登録）")

    def test_directory_auto_created(self) -> None:
        self.assertFalse(self.result_path.parent.exists())
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "environment",
            "--error", "x",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.result_path.exists())

    def test_missing_required_for_ok(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/x.md",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("required", result.stderr)
        self.assertFalse(self.result_path.exists())

    def test_missing_required_for_error(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "git",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("required", result.stderr)

    def test_worktree_path_required_when_not_removed(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "x.md",
            "--draft-url", "https://x",
            "--pr-url", "https://y",
            "--worktree-removed", "false",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("worktree-path", result.stderr)

    def test_overwrite_existing_file(self) -> None:
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        self.result_path.write_text('{"old":"data"}\n', encoding="utf-8")
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "environment",
            "--error", "x",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["status"], "error")
        self.assertNotIn("old", data)


if __name__ == "__main__":
    unittest.main()
