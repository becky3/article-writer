"""auto_publish_diary.py（orchestrator）の単体テスト.

仕様: .claude/skills/auto-publish-diary/SKILL.md
方針: git/gh の subprocess を伴う Phase は統合レベルのため対象外。
本テストは純粋ロジック（PR 本文組み立て・result.json 書き込みの単一経路 fail/finish）を検証する。

実行:

    python -m unittest tests.test_auto_publish_diary
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

# scripts/ を import path に追加
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import auto_publish_diary  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class BuildPrBodyTest(unittest.TestCase):
    def test_replaces_all_placeholders_against_real_template(self) -> None:
        body = auto_publish_diary.build_pr_body(
            str(REPO_ROOT),
            title="配属初日の記録",
            date="2026-03-14",
            article_path="articles/hatena/2026-03-14-diary.md",
            edit_url="https://blog.hatena.ne.jp/ID/blog.hatenablog.com/edit?entry=123",
            public_url="https://blog.hatenablog.com/entry/2026/03/14/000000",
        )
        self.assertIn("配属初日の記録", body)
        self.assertIn("2026-03-14", body)
        self.assertIn("edit?entry=123", body)
        self.assertIn("/entry/2026/03/14/000000", body)
        self.assertIn("articles/hatena/2026-03-14-diary.md", body)
        # 未置換プレースホルダが残っていないこと
        self.assertNotIn("{{", body)
        self.assertNotIn("}}", body)

    def test_special_characters_replaced_literally(self) -> None:
        # & \ | $ 等が含まれても str.replace でリテラル置換される
        body = auto_publish_diary.build_pr_body(
            str(REPO_ROOT),
            title=r"A&B \back |pipe $VAR",
            date="2026-03-14",
            article_path="articles/hatena/2026-03-14-diary.md",
            edit_url="https://e/edit?entry=1&x=2",
            public_url="https://p/entry/2026/03/14/000000",
        )
        self.assertIn(r"A&B \back |pipe $VAR", body)
        self.assertIn("edit?entry=1&x=2", body)


class FailFinishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.parent_repo = self.tmpdir.name
        self.result_path = (
            pathlib.Path(self.parent_repo) / ".tmp" / "auto-publish-diary" / "result.json"
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _read(self) -> dict:
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def test_fail_writes_error_result_and_exits_1(self) -> None:
        state = auto_publish_diary.PublishState(
            parent_repo=self.parent_repo,
            worktree_path="D:/wt/x",
            article_path="articles/hatena/2026-03-14-diary.md",
        )
        with self.assertRaises(SystemExit) as cm:
            auto_publish_diary.fail(state, failed_phase="git", error="git push に失敗")
        self.assertEqual(cm.exception.code, 1)
        data = self._read()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["failed_phase"], "git")
        self.assertEqual(data["error"], "git push に失敗")
        self.assertEqual(data["article_path"], "articles/hatena/2026-03-14-diary.md")
        self.assertEqual(data["worktree_path"], "D:/wt/x")
        self.assertEqual(data["merged"], False)
        self.assertEqual(data["worktree_removed"], False)
        # 未到達フィールドは null
        self.assertIsNone(data["edit_url"])
        self.assertIsNone(data["pr_url"])

    def test_finish_writes_ok_result_removed(self) -> None:
        state = auto_publish_diary.PublishState(
            parent_repo=self.parent_repo,
            worktree_path="D:/wt/x",
            article_path="articles/hatena/2026-03-14-diary.md",
            edit_url="https://e/edit?entry=1",
            public_url="https://p/entry/2026/03/14/000000",
            pr_url="https://github.com/becky3/article-writer/pull/1",
        )
        auto_publish_diary.finish(state, worktree_removed=True)
        data = self._read()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["edit_url"], "https://e/edit?entry=1")
        self.assertEqual(data["public_url"], "https://p/entry/2026/03/14/000000")
        self.assertEqual(data["merged"], True)
        self.assertEqual(data["worktree_removed"], True)
        # 削除済みなら worktree_path は null に正規化される
        self.assertIsNone(data["worktree_path"])

    def test_finish_keeps_worktree_path_when_not_removed(self) -> None:
        state = auto_publish_diary.PublishState(
            parent_repo=self.parent_repo,
            worktree_path="D:/wt/x",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
        )
        auto_publish_diary.finish(state, worktree_removed=False)
        data = self._read()
        self.assertEqual(data["worktree_removed"], False)
        self.assertEqual(data["worktree_path"], "D:/wt/x")


if __name__ == "__main__":
    unittest.main()
