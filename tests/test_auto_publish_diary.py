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


class SweepStaleAutoWorktreesTest(unittest.TestCase):
    """setup の前回残骸掃除（#245 の翌日収束用の安全網）を検証する。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.parent_dir = pathlib.Path(self.tmpdir.name)
        self.parent_repo = self.parent_dir / "article-writer"
        self.parent_repo.mkdir()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _sweep(self) -> mock.MagicMock:
        with mock.patch.object(auto_publish_diary, "_run") as run_mock:
            auto_publish_diary.sweep_stale_auto_worktrees(
                str(self.parent_repo), "article-writer", str(self.parent_dir)
            )
        return run_mock

    def test_prunes_worktree_registrations(self) -> None:
        run_mock = self._sweep()
        run_mock.assert_called_once_with(
            ["git", "-C", str(self.parent_repo), "worktree", "prune"]
        )

    def test_removes_empty_stale_dirs_only(self) -> None:
        empty_stale = self.parent_dir / "article-writer-wt-auto-20260716"
        empty_stale.mkdir()
        nonempty_stale = self.parent_dir / "article-writer-wt-auto-20260715"
        nonempty_stale.mkdir()
        (nonempty_stale / "articles").mkdir()
        unrelated = self.parent_dir / "article-writer-wt-123"
        unrelated.mkdir()

        self._sweep()

        self.assertFalse(empty_stale.exists(), "空の残骸は削除される")
        self.assertTrue(nonempty_stale.exists(), "非空の残骸は未リカバリ記事保護のため残す")
        self.assertTrue(unrelated.exists(), "auto 以外の worktree ディレクトリは対象外")

    def test_ignores_matching_files(self) -> None:
        stray_file = self.parent_dir / "article-writer-wt-auto-20260716"
        stray_file.write_text("not a dir", encoding="utf-8")
        self._sweep()
        self.assertTrue(stray_file.exists())

    def test_prunes_again_after_removing_dirs(self) -> None:
        """空ディレクトリを削除した場合、ダングリング登録を刈るため prune を再実行する。"""
        (self.parent_dir / "article-writer-wt-auto-20260716").mkdir()
        run_mock = self._sweep()
        prune_cmd = ["git", "-C", str(self.parent_repo), "worktree", "prune"]
        self.assertEqual(
            [c.args[0] for c in run_mock.call_args_list], [prune_cmd, prune_cmd]
        )


class CreateInFlightMarkerTest(unittest.TestCase):
    """setup 成功時のマーカー作成・カウンタリセット・セッション ID 記録（Stop hook ガードの前提）を検証する。"""

    def test_creates_marker_and_resets_counter_and_records_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            state_dir = pathlib.Path(d) / ".tmp" / "auto-publish-diary"
            state_dir.mkdir(parents=True)
            counter = state_dir / "stop-block-count"
            counter.write_text("2\n", encoding="utf-8")

            with mock.patch.dict(
                auto_publish_diary.os.environ,
                {"CLAUDE_CODE_SESSION_ID": "sid-12345"},
            ):
                auto_publish_diary.create_in_flight_marker(d, "2026-07-17T04:30:00")

            marker = state_dir / "in-flight"
            self.assertEqual(
                marker.read_text(encoding="utf-8"), "2026-07-17T04:30:00\n"
            )
            self.assertFalse(counter.exists(), "前回カウンタはリセット（削除）される")
            self.assertEqual(
                (state_dir / "session-id").read_text(encoding="utf-8"), "sid-12345\n"
            )

    def test_removes_stale_session_id_when_env_missing(self) -> None:
        """env 不在（claude 外の手動実行等）では記録せず、前回残骸の古い ID も残さない。

        古い ID が残ると無関係セッションの誤ブロックにつながるため、必ず消してから判定する。
        """
        with tempfile.TemporaryDirectory() as d:
            state_dir = pathlib.Path(d) / ".tmp" / "auto-publish-diary"
            state_dir.mkdir(parents=True)
            stale = state_dir / "session-id"
            stale.write_text("old-sid\n", encoding="utf-8")

            env = {
                k: v
                for k, v in auto_publish_diary.os.environ.items()
                if k != "CLAUDE_CODE_SESSION_ID"
            }
            with mock.patch.dict(auto_publish_diary.os.environ, env, clear=True):
                auto_publish_diary.create_in_flight_marker(d, "2026-07-17T04:30:00")

            self.assertFalse(stale.exists())
            self.assertTrue((state_dir / "in-flight").exists())


class ResolveContextTest(unittest.TestCase):
    """finalize --worktree 指定時のコンテキスト導出（親リポ cwd からの起動対応）を検証する。"""

    def _make_proc(self, stdout: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    def test_resolves_from_worktree_arg_with_absolute_common_dir(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            parent = pathlib.Path(d) / "article-writer"
            worktree = pathlib.Path(d) / "article-writer-wt-auto-20260717"
            worktree.mkdir()
            common_dir = str(parent / ".git")
            with mock.patch.object(auto_publish_diary, "_run") as run_mock:
                run_mock.side_effect = [
                    self._make_proc(common_dir + "\n"),
                    self._make_proc("auto/diary-2026-07-17\n"),
                ]
                parent_repo, worktree_path, branch = auto_publish_diary._resolve_context(
                    str(worktree)
                )
            self.assertEqual(parent_repo, str(parent))
            self.assertEqual(worktree_path, str(worktree.resolve()))
            self.assertEqual(branch, "auto/diary-2026-07-17")
            # git 呼び出しは -C <worktree> 基準で行われる（cwd 非依存）
            self.assertEqual(
                run_mock.call_args_list[0].args[0][:3], ["git", "-C", str(worktree.resolve())]
            )

    def test_raises_when_worktree_is_not_a_git_repo(self) -> None:
        """prune 済み残骸等の git 管理外ディレクトリで parent_repo が誤導出されない。

        検査なしだと realpath("") = cwd 起点で親リポの一つ上に誤導出され、result.json が
        不可視の場所に書かれる（code-review 指摘）。RuntimeError で environment 失敗に合流させる。
        """
        with tempfile.TemporaryDirectory() as d:
            for proc in (
                self._make_proc(""),  # returncode 0 でも出力空
                subprocess.CompletedProcess(
                    args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
                ),
            ):
                with mock.patch.object(auto_publish_diary, "_run", return_value=proc):
                    with self.assertRaises(RuntimeError):
                        auto_publish_diary._resolve_context(d)

    def test_raises_when_branch_name_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(auto_publish_diary, "_run") as run_mock:
                run_mock.side_effect = [
                    self._make_proc(str(pathlib.Path(d) / ".git") + "\n"),
                    self._make_proc(""),
                ]
                with self.assertRaises(RuntimeError):
                    auto_publish_diary._resolve_context(d)


class FinalizeGuardTest(unittest.TestCase):
    """cmd_finalize の起動ミス検出ガード（--worktree 不在 / スクリプト起動元ズレ）を検証する。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.parent_repo = pathlib.Path(self.tmpdir.name)
        self.result_path = (
            self.parent_repo / ".tmp" / "auto-publish-diary" / "result.json"
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _read(self) -> dict:
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def test_fails_environment_when_worktree_path_missing(self) -> None:
        missing = str(self.parent_repo / "no-such-worktree")
        with mock.patch.object(auto_publish_diary, "_run") as run_mock:
            # _fallback_parent_repo の --git-common-dir 呼び出しに親リポの .git を返す
            run_mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=str(self.parent_repo / ".git") + "\n", stderr=""
            )
            with self.assertRaises(SystemExit) as cm:
                auto_publish_diary.cmd_finalize("articles/hatena/x.md", worktree=missing)
        self.assertEqual(cm.exception.code, 1)
        data = self._read()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["failed_phase"], "environment")
        self.assertIn("no-such-worktree", data["error"])

    def test_fails_environment_when_script_root_mismatches_worktree(self) -> None:
        """親リポ側スクリプト起動の取り違え（publish_hatena の読み先ズレ）を検出する。"""
        worktree = self.parent_repo / "wt"
        worktree.mkdir()
        with (
            mock.patch.object(
                auto_publish_diary,
                "_resolve_context",
                return_value=(str(self.parent_repo), str(worktree), "auto/diary-x"),
            ),
            mock.patch.object(
                auto_publish_diary.publish_hatena,
                "REPO_ROOT",
                self.parent_repo / "elsewhere",
            ),
        ):
            with self.assertRaises(SystemExit) as cm:
                auto_publish_diary.cmd_finalize(
                    "articles/hatena/x.md", worktree=str(worktree)
                )
        self.assertEqual(cm.exception.code, 1)
        data = self._read()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["failed_phase"], "environment")
        self.assertIn("worktree 側の scripts/auto_publish_diary.py", data["error"])


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
