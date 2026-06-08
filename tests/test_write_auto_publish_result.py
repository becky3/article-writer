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

# scripts/ を import path に追加（関数 API の直接テスト用）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import write_auto_publish_result  # noqa: E402

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
            "--edit-url", "https://blog.hatena.ne.jp/ID/blog.hatenablog.com/edit?entry=123",
            "--public-url", "https://blog.example.com/entry/2026/05/20/000000",
            "--pr-url", "https://github.com/becky3/article-writer/pull/99",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data, {
            "status": "ok",
            "article_path": "articles/hatena/2026-05-20-diary.md",
            "edit_url": "https://blog.hatena.ne.jp/ID/blog.hatenablog.com/edit?entry=123",
            "public_url": "https://blog.example.com/entry/2026/05/20/000000",
            "pr_url": "https://github.com/becky3/article-writer/pull/99",
            "merged": True,
            "worktree_removed": True,
            "worktree_path": None,
            "worktree_remove_error": None,
        })

    def test_success_with_worktree_not_removed(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--edit-url", "https://blog.hatena.ne.jp/ID/blog.hatenablog.com/edit?entry=456",
            "--public-url", "https://blog.example.com/entry/2026/05/20/000000",
            "--pr-url", "https://github.com/becky3/article-writer/pull/100",
            "--worktree-removed", "false",
            "--worktree-path", "D:/GitHub/becky3/article-writer-wt-auto-20260520",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["worktree_removed"], False)
        self.assertEqual(data["worktree_path"], "D:/GitHub/becky3/article-writer-wt-auto-20260520")
        self.assertIsNone(data["worktree_remove_error"])

    def test_success_with_worktree_remove_error_via_cli(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--edit-url", "https://blog.hatena.ne.jp/ID/b/edit?entry=1",
            "--public-url", "https://blog/entry/2026/05/20/000000",
            "--pr-url", "https://github.com/becky3/article-writer/pull/101",
            "--worktree-removed", "false",
            "--worktree-path", "D:/wt/x",
            "--worktree-remove-error", "fatal: 'D:/wt/x' is not a working tree",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(
            data["worktree_remove_error"], "fatal: 'D:/wt/x' is not a working tree"
        )

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
            "edit_url": None,
            "public_url": None,
            "pr_url": None,
            "merged": False,
            "worktree_removed": False,
            "worktree_path": None,
            "worktree_remove_error": None,
        })

    def test_error_with_partial_progress(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "error",
            "--failed-phase", "git",
            "--error", "gh pr merge exit 1",
            "--worktree-path", "D:/wt/x",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--edit-url", "https://blog.hatena.ne.jp/ID/b/edit?entry=1",
            "--public-url", "https://blog/entry/2026/05/20/000000",
            "--pr-url", "https://github.com/.../pull/1",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["failed_phase"], "git")
        self.assertEqual(data["pr_url"], "https://github.com/.../pull/1")
        self.assertEqual(data["merged"], False)
        self.assertEqual(data["worktree_removed"], False)

    def test_special_characters_in_values(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "articles/hatena/2026-05-20-diary.md",
            "--edit-url", "https://blog/entry?a=1&b=\"quoted\"&c=back\\slash&d=$VAR",
            "--public-url", "https://blog/entry/2026/05/20/000000",
            "--pr-url", "https://github.com/.../pull/1",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self._read_result()
        self.assertEqual(data["edit_url"], "https://blog/entry?a=1&b=\"quoted\"&c=back\\slash&d=$VAR")

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
            "--edit-url", "https://x",
            "--public-url", "https://x2",
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

    def test_no_temp_file_left_after_success(self) -> None:
        result = run_script([
            "--parent-repo", str(self.parent_repo),
            "--status", "ok",
            "--article-path", "x.md",
            "--edit-url", "https://x",
            "--public-url", "https://x2",
            "--pr-url", "https://y",
            "--worktree-removed", "true",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        leftover = list(self.result_path.parent.glob(".result.json.*"))
        self.assertEqual(leftover, [], f"atomic write temp files left behind: {leftover}")


class BuildResultFunctionTest(unittest.TestCase):
    """orchestrator が import して使う build_result / write_result_file の直接テスト。"""

    def test_build_result_ok_normalizes_worktree_path_when_removed(self) -> None:
        result = write_auto_publish_result.build_result(
            status="ok",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
            worktree_removed=True,
            worktree_path="D:/wt/x",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["edit_url"], "https://e")
        self.assertEqual(result["public_url"], "https://p")
        self.assertEqual(result["merged"], True)
        self.assertEqual(result["worktree_removed"], True)
        self.assertIsNone(result["worktree_path"])

    def test_build_result_ok_with_worktree_remove_error(self) -> None:
        result = write_auto_publish_result.build_result(
            status="ok",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
            worktree_removed=False,
            worktree_path="D:/wt/x",
            worktree_remove_error="fatal: cannot remove 'D:/wt/x'",
        )
        self.assertEqual(result["worktree_removed"], False)
        self.assertEqual(result["worktree_path"], "D:/wt/x")
        self.assertEqual(result["worktree_remove_error"], "fatal: cannot remove 'D:/wt/x'")

    def test_build_result_ok_preserves_remove_error_when_removed(self) -> None:
        """rmdir フォールバック発動シグナル経路（#245）.

        worktree_removed=True かつ worktree_remove_error 非 null の組み合わせは
        「git remove は失敗したが rmdir フォールバックで救済された」ことを表すシグナル。
        正規化（None 化）してしまうと根本原因の継続観測ができなくなるため、ここで保持する。
        """
        result = write_auto_publish_result.build_result(
            status="ok",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
            worktree_removed=True,
            worktree_remove_error="error: failed to delete '/wt/x': Permission denied",
        )
        self.assertEqual(
            result["worktree_remove_error"],
            "error: failed to delete '/wt/x': Permission denied",
        )
        # 成功時は worktree_path は None に正規化される（既存仕様）
        self.assertIsNone(result["worktree_path"])

    def test_build_result_error_includes_remove_error_field_as_null(self) -> None:
        # スキーマ均一化: error 時も worktree_remove_error キーは存在し None
        result = write_auto_publish_result.build_result(
            status="error",
            failed_phase="publish",
            error="HTTP 401",
        )
        self.assertIn("worktree_remove_error", result)
        self.assertIsNone(result["worktree_remove_error"])

    def test_build_result_error_includes_partial_fields(self) -> None:
        result = write_auto_publish_result.build_result(
            status="error",
            failed_phase="publish",
            error="HTTP 401",
            article_path="a.md",
            worktree_path="D:/wt/x",
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failed_phase"], "publish")
        self.assertEqual(result["merged"], False)
        self.assertEqual(result["worktree_removed"], False)
        self.assertIsNone(result["edit_url"])
        self.assertIsNone(result["public_url"])

    def test_write_result_file_atomic_no_leftover(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            result = write_auto_publish_result.build_result(
                status="ok",
                article_path="a.md",
                edit_url="https://e",
                public_url="https://p",
                pr_url="https://pr",
                worktree_removed=True,
            )
            write_auto_publish_result.write_result_file(d, result)
            target = pathlib.Path(d) / ".tmp" / "auto-publish-diary" / "result.json"
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["status"], "ok")
            leftover = list(target.parent.glob(".result.json.*"))
            self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
