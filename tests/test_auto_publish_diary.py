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
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        # 既定では remove_error は None
        self.assertIsNone(data["worktree_remove_error"])

    def test_finish_records_worktree_remove_error(self) -> None:
        state = auto_publish_diary.PublishState(
            parent_repo=self.parent_repo,
            worktree_path="D:/wt/x",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
        )
        auto_publish_diary.finish(
            state,
            worktree_removed=False,
            worktree_remove_error="fatal: 'D:/wt/x' is not a working tree",
        )
        data = self._read()
        self.assertEqual(data["worktree_removed"], False)
        self.assertEqual(
            data["worktree_remove_error"], "fatal: 'D:/wt/x' is not a working tree"
        )

    def test_finish_keeps_remove_error_on_rmdir_fallback(self) -> None:
        """rmdir フォールバック発動シグナル経路（#245）: removed=True でも stderr を保持する。"""
        state = auto_publish_diary.PublishState(
            parent_repo=self.parent_repo,
            worktree_path="D:/wt/x",
            article_path="a.md",
            edit_url="https://e",
            public_url="https://p",
            pr_url="https://pr",
        )
        auto_publish_diary.finish(
            state,
            worktree_removed=True,
            worktree_remove_error="error: failed to delete 'D:/wt/x': Permission denied",
        )
        data = self._read()
        self.assertEqual(data["worktree_removed"], True)
        self.assertEqual(
            data["worktree_remove_error"],
            "error: failed to delete 'D:/wt/x': Permission denied",
        )
        # 削除済みフラグ系は従前どおり None 化される
        self.assertIsNone(data["worktree_path"])


class CleanupTest(unittest.TestCase):
    """`cleanup()` の戻り値分岐（#245 Windows rmdir フォールバック）を検証する。

    本番事象（Windows での `git worktree remove --force` の rmdir 段階失敗）は CI Linux 環境で
    再現できないため、subprocess / os 呼び出しを mock してフォールバック分岐の論理整合のみを担保する。
    """

    def _make_proc(
        self, returncode: int, stderr: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        )

    def test_returns_true_when_git_remove_succeeds(self) -> None:
        with (
            mock.patch.object(auto_publish_diary, "_run") as run_mock,
            mock.patch.object(auto_publish_diary.os, "chdir"),
            mock.patch.object(auto_publish_diary.os, "listdir") as listdir_mock,
            mock.patch.object(auto_publish_diary.os, "rmdir") as rmdir_mock,
            mock.patch.object(auto_publish_diary.time, "sleep") as sleep_mock,
        ):
            run_mock.side_effect = [self._make_proc(0), self._make_proc(0), self._make_proc(0)]
            removed, error = auto_publish_diary.cleanup(
                "/parent", "/parent/wt-x", "feature/x"
            )
        self.assertTrue(removed)
        self.assertIsNone(error)
        listdir_mock.assert_not_called()
        rmdir_mock.assert_not_called()
        # git remove 成功経路ではフォールバックも sleep も発生しないことを固定
        sleep_mock.assert_not_called()

    def test_falls_back_to_rmdir_when_dir_is_empty(self) -> None:
        with (
            mock.patch.object(auto_publish_diary, "_run") as run_mock,
            mock.patch.object(auto_publish_diary.os, "chdir"),
            mock.patch.object(auto_publish_diary.os.path, "isdir", return_value=True),
            mock.patch.object(auto_publish_diary.os, "listdir", return_value=[]) as listdir_mock,
            mock.patch.object(auto_publish_diary.os, "rmdir") as rmdir_mock,
            mock.patch.object(auto_publish_diary.time, "sleep") as sleep_mock,
        ):
            run_mock.side_effect = [
                self._make_proc(1, "error: failed to delete '/parent/wt-x': Permission denied"),
                self._make_proc(0),
                self._make_proc(0),
            ]
            removed, error = auto_publish_diary.cleanup(
                "/parent", "/parent/wt-x", "feature/x"
            )
        self.assertTrue(removed)
        self.assertEqual(
            error, "error: failed to delete '/parent/wt-x': Permission denied"
        )
        listdir_mock.assert_called_once_with("/parent/wt-x")
        rmdir_mock.assert_called_once_with("/parent/wt-x")
        # 初回試行で成功する経路では sleep を呼ばないことを固定（不要な待機を避ける）
        sleep_mock.assert_not_called()
        # rmdir フォールバック後も branch -D / pull --ff-only が従前通り呼ばれることを固定する
        self.assertEqual(len(run_mock.call_args_list), 3)
        self.assertEqual(
            run_mock.call_args_list[0].args[0],
            ["git", "-C", "/parent", "worktree", "remove", "--force", "/parent/wt-x"],
        )
        self.assertEqual(
            run_mock.call_args_list[1].args[0],
            ["git", "-C", "/parent", "branch", "-D", "feature/x"],
        )
        self.assertEqual(
            run_mock.call_args_list[2].args[0],
            ["git", "-C", "/parent", "pull", "--ff-only", "origin", "main"],
        )

    def test_returns_false_when_rmdir_raises_oserror_after_all_retries(self) -> None:
        """rmdir が上限まで連続 OSError を投げた場合に最終的に諦め silent 脱出することを確認。

        PR #246 の単発フォールバックでは PR #247 で再失敗を観測したため、リトライ + バックオフへ
        変更（#245 追加対応）。本テストは上限回数まで連続失敗するシナリオを担保する。
        """
        with (
            mock.patch.object(auto_publish_diary, "_run") as run_mock,
            mock.patch.object(auto_publish_diary.os, "chdir"),
            mock.patch.object(auto_publish_diary.os.path, "isdir", return_value=True),
            mock.patch.object(auto_publish_diary.os, "listdir", return_value=[]),
            mock.patch.object(
                auto_publish_diary.os, "rmdir", side_effect=PermissionError("denied")
            ) as rmdir_mock,
            mock.patch.object(auto_publish_diary.time, "sleep") as sleep_mock,
        ):
            run_mock.side_effect = [
                self._make_proc(1, "error: failed to delete '/parent/wt-x': Permission denied"),
                self._make_proc(0),
                self._make_proc(0),
            ]
            removed, error = auto_publish_diary.cleanup(
                "/parent", "/parent/wt-x", "feature/x"
            )
        self.assertFalse(removed)
        self.assertEqual(
            error, "error: failed to delete '/parent/wt-x': Permission denied"
        )
        self.assertEqual(rmdir_mock.call_count, auto_publish_diary.MAX_RMDIR_ATTEMPTS)
        # バックオフ間隔: 試行 i のディレイは (i + 1) * RMDIR_BACKOFF_STEP。
        # 最終試行（i = MAX_RMDIR_ATTEMPTS - 1）後は sleep しないため呼び出し回数は MAX_RMDIR_ATTEMPTS - 1
        expected_sleeps = [
            mock.call((i + 1) * auto_publish_diary.RMDIR_BACKOFF_STEP)
            for i in range(auto_publish_diary.MAX_RMDIR_ATTEMPTS - 1)
        ]
        self.assertEqual(sleep_mock.call_args_list, expected_sleeps)

    def test_succeeds_when_rmdir_recovers_after_retries(self) -> None:
        """rmdir が数回 OSError → 最終的に成功するシナリオでリトライが正しく機能することを確認。

        Windows の Permission denied が数秒間持続する観察（PR #247）に対する救済経路。
        """
        # 2 回失敗後に成功するシナリオ（合計 3 回呼び出し、間に 2 回 sleep）
        with (
            mock.patch.object(auto_publish_diary, "_run") as run_mock,
            mock.patch.object(auto_publish_diary.os, "chdir"),
            mock.patch.object(auto_publish_diary.os.path, "isdir", return_value=True),
            mock.patch.object(auto_publish_diary.os, "listdir", return_value=[]),
            mock.patch.object(
                auto_publish_diary.os,
                "rmdir",
                side_effect=[PermissionError("denied"), PermissionError("denied"), None],
            ) as rmdir_mock,
            mock.patch.object(auto_publish_diary.time, "sleep") as sleep_mock,
        ):
            run_mock.side_effect = [
                self._make_proc(1, "error: failed to delete '/parent/wt-x': Permission denied"),
                self._make_proc(0),
                self._make_proc(0),
            ]
            removed, error = auto_publish_diary.cleanup(
                "/parent", "/parent/wt-x", "feature/x"
            )
        self.assertTrue(removed)
        # remove_error は git の元 stderr を保持（フォールバック発動シグナル）
        self.assertEqual(
            error, "error: failed to delete '/parent/wt-x': Permission denied"
        )
        self.assertEqual(rmdir_mock.call_count, 3)
        # 失敗 2 回の間に sleep 2 回（成功した 3 回目の後は sleep しない）
        expected_sleeps = [
            mock.call(1 * auto_publish_diary.RMDIR_BACKOFF_STEP),
            mock.call(2 * auto_publish_diary.RMDIR_BACKOFF_STEP),
        ]
        self.assertEqual(sleep_mock.call_args_list, expected_sleeps)

    def test_returns_false_when_dir_not_empty(self) -> None:
        with (
            mock.patch.object(auto_publish_diary, "_run") as run_mock,
            mock.patch.object(auto_publish_diary.os, "chdir"),
            mock.patch.object(auto_publish_diary.os.path, "isdir", return_value=True),
            mock.patch.object(
                auto_publish_diary.os, "listdir", return_value=["stray.txt"]
            ),
            mock.patch.object(auto_publish_diary.os, "rmdir") as rmdir_mock,
            mock.patch.object(auto_publish_diary.time, "sleep") as sleep_mock,
        ):
            run_mock.side_effect = [
                self._make_proc(1, "error: failed to delete '/parent/wt-x': Permission denied"),
                self._make_proc(0),
                self._make_proc(0),
            ]
            removed, error = auto_publish_diary.cleanup(
                "/parent", "/parent/wt-x", "feature/x"
            )
        self.assertFalse(removed)
        self.assertEqual(
            error, "error: failed to delete '/parent/wt-x': Permission denied"
        )
        rmdir_mock.assert_not_called()
        # 非空 dir 経路では初回 iteration で break するため sleep も発生しないことを固定
        sleep_mock.assert_not_called()


class SummarizeStderrTest(unittest.TestCase):
    def test_returns_none_for_empty(self) -> None:
        self.assertIsNone(auto_publish_diary._summarize_stderr(None))
        self.assertIsNone(auto_publish_diary._summarize_stderr(""))
        self.assertIsNone(auto_publish_diary._summarize_stderr("   \n\n  "))

    def test_collapses_multiline_to_single_line(self) -> None:
        self.assertEqual(
            auto_publish_diary._summarize_stderr("line1\nline2\n   line3  "),
            "line1 line2 line3",
        )


if __name__ == "__main__":
    unittest.main()
