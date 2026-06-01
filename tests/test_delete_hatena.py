"""delete_hatena.py の主要関数のユニットテスト.

仕様: aidlc-archive/178/plan-work/issue-178.md (テスト方針)

実行:

    python -m unittest tests.test_delete_hatena
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import delete_hatena  # noqa: E402


class ParseDateArgTest(unittest.TestCase):
    def test_single_date_returns_one_element_with_is_range_false(self) -> None:
        dates, is_range = delete_hatena.parse_date_arg("2026-05-13")
        self.assertEqual(dates, ["2026-05-13"])
        self.assertFalse(is_range)

    def test_single_date_invalid_value_raises(self) -> None:
        with self.assertRaises(SystemExit):
            delete_hatena.parse_date_arg("2026-99-99")

    def test_invalid_format_raises(self) -> None:
        with self.assertRaises(SystemExit):
            delete_hatena.parse_date_arg("invalid")

    def test_range_expanded_with_is_range_true(self) -> None:
        dates, is_range = delete_hatena.parse_date_arg("2026-05-01..2026-05-03")
        self.assertEqual(dates, ["2026-05-01", "2026-05-02", "2026-05-03"])
        self.assertTrue(is_range)

    def test_same_day_range_is_marked_as_range(self) -> None:
        dates, is_range = delete_hatena.parse_date_arg("2026-05-13..2026-05-13")
        self.assertEqual(dates, ["2026-05-13"])
        self.assertTrue(is_range)

    def test_start_after_end_raises(self) -> None:
        with self.assertRaises(SystemExit):
            delete_hatena.parse_date_arg("2026-05-10..2026-05-01")

    def test_range_invalid_value_raises(self) -> None:
        with self.assertRaises(SystemExit):
            delete_hatena.parse_date_arg("2026-13-01..2026-13-05")


class RewritePublishedJsonlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.jsonl_path = pathlib.Path(self.tmpdir.name) / "published.jsonl"

    def _write(self, lines: list[dict]) -> None:
        text = "\n".join(json.dumps(o, ensure_ascii=False) for o in lines) + "\n"
        self.jsonl_path.write_text(text, encoding="utf-8")

    def _read(self) -> list[dict]:
        return [
            json.loads(line)
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_remove_dates_drops_matching_lines(self) -> None:
        self._write([
            {"date": "2026-05-01", "title": "A", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "B", "edit_url": "u2"},
            {"date": "2026-05-03", "title": "C", "edit_url": "u3"},
        ])
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path):
            delete_hatena.rewrite_published_jsonl(
                remove_dates={"2026-05-02"}, nullify_dates=set()
            )
        remaining = self._read()
        self.assertEqual([e["date"] for e in remaining], ["2026-05-01", "2026-05-03"])

    def test_nullify_dates_sets_edit_url_null(self) -> None:
        self._write([
            {"date": "2026-05-01", "title": "A", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "B", "edit_url": "u2"},
        ])
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path):
            delete_hatena.rewrite_published_jsonl(
                remove_dates=set(), nullify_dates={"2026-05-02"}
            )
        remaining = self._read()
        self.assertEqual(remaining[0]["edit_url"], "u1")
        self.assertIsNone(remaining[1]["edit_url"])

    def test_malformed_json_line_is_preserved(self) -> None:
        text = (
            json.dumps({"date": "2026-05-01", "title": "A", "edit_url": "u1"}) + "\n"
            + "BROKEN LINE\n"
            + json.dumps({"date": "2026-05-02", "title": "B", "edit_url": "u2"}) + "\n"
        )
        self.jsonl_path.write_text(text, encoding="utf-8")
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path):
            delete_hatena.rewrite_published_jsonl(
                remove_dates={"2026-05-02"}, nullify_dates=set()
            )
        lines = self.jsonl_path.read_text(encoding="utf-8").splitlines()
        self.assertIn("BROKEN LINE", lines)

    def test_missing_file_returns_silently(self) -> None:
        missing = pathlib.Path(self.tmpdir.name) / "missing.jsonl"
        with patch.object(delete_hatena, "PUBLISHED_JSONL", missing):
            delete_hatena.rewrite_published_jsonl(
                remove_dates={"2026-05-01"}, nullify_dates=set()
            )
        self.assertFalse(missing.exists())


class BuildTargetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.articles_dir = pathlib.Path(self.tmpdir.name) / "articles"
        self.articles_dir.mkdir()

    def _make_article(self, date: str, title: str) -> None:
        path = self.articles_dir / f"{date}-diary.md"
        path.write_text(
            f"---\ntitle: \"{title}\"\ndate: \"{date}\"\n---\n\n# {title}\n",
            encoding="utf-8",
        )

    def test_single_date_with_existing_md(self) -> None:
        self._make_article("2026-05-01", "title-a")
        with patch.object(delete_hatena, "ARTICLES_DIR", self.articles_dir), \
             patch.object(delete_hatena, "lookup_published", return_value=None):
            targets, skipped = delete_hatena.build_targets(
                ["2026-05-01"], is_range=False
            )
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].date, "2026-05-01")
        self.assertEqual(skipped, [])

    def test_single_date_missing_md_raises(self) -> None:
        with patch.object(delete_hatena, "ARTICLES_DIR", self.articles_dir), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "lookup_published", return_value=None):
            with self.assertRaises(SystemExit):
                delete_hatena.build_targets(["2026-05-01"], is_range=False)

    def test_range_missing_md_is_skipped(self) -> None:
        self._make_article("2026-05-01", "title-a")
        self._make_article("2026-05-03", "title-c")
        with patch.object(delete_hatena, "ARTICLES_DIR", self.articles_dir), \
             patch.object(delete_hatena, "lookup_published", return_value=None):
            targets, skipped = delete_hatena.build_targets(
                ["2026-05-01", "2026-05-02", "2026-05-03"], is_range=True
            )
        self.assertEqual([t.date for t in targets], ["2026-05-01", "2026-05-03"])
        self.assertEqual(skipped, ["2026-05-02"])

    def test_range_all_missing_returns_empty(self) -> None:
        with patch.object(delete_hatena, "ARTICLES_DIR", self.articles_dir), \
             patch.object(delete_hatena, "lookup_published", return_value=None):
            targets, skipped = delete_hatena.build_targets(
                ["2026-05-01", "2026-05-02"], is_range=True
            )
        self.assertEqual(targets, [])
        self.assertEqual(skipped, ["2026-05-01", "2026-05-02"])


class ValidateTargetsForModeTest(unittest.TestCase):
    def _make_target(self, date: str, edit_url: str | None) -> delete_hatena.Target:
        entry = (
            {"date": date, "title": "t", "edit_url": edit_url}
            if edit_url is not None or date.startswith("none-")
            else None
        )
        return delete_hatena.Target(
            date=date,
            article_path=pathlib.Path(f"/tmp/{date}.md"),
            title="t",
            entry=entry,
        )

    def test_remote_only_with_all_edit_urls_passes(self) -> None:
        targets = [
            self._make_target("2026-05-01", "u1"),
            self._make_target("2026-05-02", "u2"),
        ]
        delete_hatena.validate_targets_for_mode(targets, remote_only=True)

    def test_remote_only_with_null_edit_url_raises(self) -> None:
        targets = [
            self._make_target("2026-05-01", "u1"),
            self._make_target("2026-05-02", None),
        ]
        with self.assertRaises(SystemExit):
            delete_hatena.validate_targets_for_mode(targets, remote_only=True)

    def test_default_mode_passes_with_null_edit_url(self) -> None:
        targets = [
            self._make_target("2026-05-01", None),
        ]
        delete_hatena.validate_targets_for_mode(targets, remote_only=False)


class DeleteRemoteEntryTest(unittest.TestCase):
    """delete_remote_entry の HTTP 例外分岐をテスト. _atompub_request を mock."""

    def test_204_no_content_succeeds(self) -> None:
        with patch.object(
            delete_hatena, "_atompub_request", return_value=(204, b"")
        ):
            delete_hatena.delete_remote_entry(
                edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
            )

    def test_200_succeeds(self) -> None:
        with patch.object(
            delete_hatena, "_atompub_request", return_value=(200, b"")
        ):
            delete_hatena.delete_remote_entry(
                edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
            )

    def test_404_raises_with_specific_message(self) -> None:
        err = urllib.error.HTTPError(
            url="https://example.com/e/1",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with patch.object(delete_hatena, "_atompub_request", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                delete_hatena.delete_remote_entry(
                    edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
                )
        self.assertIn("404", str(ctx.exception))
        self.assertIn("見つかりません", str(ctx.exception))

    def test_500_raises(self) -> None:
        err = urllib.error.HTTPError(
            url="https://example.com/e/1",
            code=500,
            msg="Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with patch.object(delete_hatena, "_atompub_request", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                delete_hatena.delete_remote_entry(
                    edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
                )
        self.assertIn("500", str(ctx.exception))

    def test_network_error_raises(self) -> None:
        err = urllib.error.URLError("network down")
        with patch.object(delete_hatena, "_atompub_request", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                delete_hatena.delete_remote_entry(
                    edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
                )
        self.assertIn("ネットワーク", str(ctx.exception))

    def test_unexpected_status_raises(self) -> None:
        with patch.object(
            delete_hatena, "_atompub_request", return_value=(202, b"")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                delete_hatena.delete_remote_entry(
                    edit_url="https://example.com/e/1", hatena_id="u", api_key="k"
                )
        self.assertIn("202", str(ctx.exception))


class ProcessTargetsTest(unittest.TestCase):
    """process_targets の段階別追跡をテスト. _atompub_request と unlink を mock."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.articles_dir = pathlib.Path(self.tmpdir.name) / "articles"
        self.articles_dir.mkdir()
        self.jsonl_path = self.articles_dir / "published.jsonl"

    def _make_target(self, date: str, *, edit_url: str | None) -> delete_hatena.Target:
        path = self.articles_dir / f"{date}-diary.md"
        path.write_text("dummy", encoding="utf-8")
        entry = {"date": date, "title": "t", "edit_url": edit_url}
        return delete_hatena.Target(
            date=date,
            article_path=path,
            title="t",
            entry=entry,
        )

    def _write_jsonl(self, lines: list[dict]) -> None:
        text = "\n".join(json.dumps(o, ensure_ascii=False) for o in lines) + "\n"
        self.jsonl_path.write_text(text, encoding="utf-8")

    def test_all_success_default_mode(self) -> None:
        targets = [
            self._make_target("2026-05-01", edit_url="u1"),
            self._make_target("2026-05-02", edit_url="u2"),
        ]
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": "u2"},
        ])
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", return_value=(200, b"")):
            results, pending, error = delete_hatena.process_targets(
                targets, remote_only=False, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertEqual(len(results), 2)
        self.assertIsNone(error)
        self.assertEqual(pending, [])
        for r in results:
            self.assertTrue(r.remote_done)
            self.assertTrue(r.local_done)
            self.assertIsNone(r.error)
        # 全行物理削除
        self.assertEqual(
            self.jsonl_path.read_text(encoding="utf-8").strip(), ""
        )

    def test_remote_only_nullifies_edit_url(self) -> None:
        target = self._make_target("2026-05-01", edit_url="u1")
        self._write_jsonl([{"date": "2026-05-01", "title": "t", "edit_url": "u1"}])
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", return_value=(204, b"")):
            results, pending, error = delete_hatena.process_targets(
                [target], remote_only=True, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertIsNone(error)
        self.assertTrue(results[0].remote_done)
        self.assertFalse(results[0].local_attempted)
        # ローカル md は残存
        self.assertTrue(target.article_path.exists())
        # jsonl は edit_url が null 化
        remaining = json.loads(self.jsonl_path.read_text(encoding="utf-8").strip())
        self.assertIsNone(remaining["edit_url"])

    def test_local_only_skips_remote(self) -> None:
        target = self._make_target("2026-05-01", edit_url="u1")
        self._write_jsonl([{"date": "2026-05-01", "title": "t", "edit_url": "u1"}])
        atompub_mock = MagicMock()
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", atompub_mock):
            results, pending, error = delete_hatena.process_targets(
                [target], remote_only=False, local_only=True,
                hatena_id="u", api_key="k",
            )
        self.assertIsNone(error)
        atompub_mock.assert_not_called()
        self.assertFalse(results[0].remote_attempted)
        self.assertTrue(results[0].local_done)
        self.assertFalse(target.article_path.exists())

    def test_failure_at_remote_keeps_local_md(self) -> None:
        """remote 失敗時、local md と jsonl 行は変更されない."""
        err = urllib.error.HTTPError(
            url="https://example.com/e/1",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        target = self._make_target("2026-05-01", edit_url="u1")
        self._write_jsonl([{"date": "2026-05-01", "title": "t", "edit_url": "u1"}])
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", side_effect=err):
            results, pending, error = delete_hatena.process_targets(
                [target], remote_only=False, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertIsNotNone(error)
        self.assertIn("404", error)
        self.assertTrue(results[0].remote_attempted)
        self.assertFalse(results[0].remote_done)
        self.assertFalse(results[0].local_attempted)
        # ローカル md は残存
        self.assertTrue(target.article_path.exists())
        # jsonl の該当行は残存
        remaining = json.loads(self.jsonl_path.read_text(encoding="utf-8").strip())
        self.assertEqual(remaining["edit_url"], "u1")

    def test_partial_failure_in_range_keeps_completed_jsonl_changes(self) -> None:
        """範囲中の部分失敗で、完了済み対象の jsonl 変更は反映される."""
        err = urllib.error.HTTPError(
            url="https://example.com/e/2",
            code=500,
            msg="Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        t1 = self._make_target("2026-05-01", edit_url="u1")
        t2 = self._make_target("2026-05-02", edit_url="u2")
        t3 = self._make_target("2026-05-03", edit_url="u3")
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": "u2"},
            {"date": "2026-05-03", "title": "t", "edit_url": "u3"},
        ])
        # 1 件目は成功、2 件目で 500 エラー
        responses = [(200, b""), err]
        def atompub_side_effect(*args, **kwargs):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", side_effect=atompub_side_effect):
            results, pending, error = delete_hatena.process_targets(
                [t1, t2, t3], remote_only=False, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertIsNotNone(error)
        self.assertEqual(len(results), 2)  # t1 完了 + t2 失敗、t3 は未実行
        self.assertIsNone(results[0].error)
        self.assertIsNotNone(results[1].error)
        self.assertEqual(pending, ["2026-05-03"])
        # t1 の jsonl 行は削除、t2/t3 は残存
        remaining_dates = [
            json.loads(line)["date"]
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(remaining_dates, ["2026-05-02", "2026-05-03"])
        # t1 のローカル md は削除、t2/t3 は残存
        self.assertFalse(t1.article_path.exists())
        self.assertTrue(t2.article_path.exists())
        self.assertTrue(t3.article_path.exists())

    def test_interval_sleeps_between_remote_deletes(self) -> None:
        """interval > 0 のとき、2 件目以降のはてな DELETE 前に time.sleep が (件数-1) 回呼ばれる."""
        targets = [
            self._make_target("2026-05-01", edit_url="u1"),
            self._make_target("2026-05-02", edit_url="u2"),
            self._make_target("2026-05-03", edit_url="u3"),
        ]
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": "u2"},
            {"date": "2026-05-03", "title": "t", "edit_url": "u3"},
        ])
        sleep_mock = MagicMock()
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena.time, "sleep", sleep_mock), \
             patch.object(delete_hatena, "_atompub_request", return_value=(204, b"")):
            results, pending, error = delete_hatena.process_targets(
                targets, remote_only=True, local_only=False,
                hatena_id="u", api_key="k", interval=2.0,
            )
        self.assertIsNone(error)
        # 3 件の DELETE のうち、待機は 1 件目の前を除く 2 回
        self.assertEqual(sleep_mock.call_count, 2)
        for call in sleep_mock.call_args_list:
            self.assertEqual(call.args, (2.0,))

    def test_interval_skips_wait_for_entries_without_edit_url(self) -> None:
        """edit_url 未登録の対象が remote 対象の間に挟まっても、待機は実 DELETE の直前にのみ入る."""
        targets = [
            self._make_target("2026-05-01", edit_url="u1"),
            self._make_target("2026-05-02", edit_url=None),
            self._make_target("2026-05-03", edit_url="u3"),
        ]
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": None},
            {"date": "2026-05-03", "title": "t", "edit_url": "u3"},
        ])
        sleep_mock = MagicMock()
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena.time, "sleep", sleep_mock), \
             patch.object(delete_hatena, "_atompub_request", return_value=(204, b"")):
            results, pending, error = delete_hatena.process_targets(
                targets, remote_only=True, local_only=False,
                hatena_id="u", api_key="k", interval=2.0,
            )
        self.assertIsNone(error)
        # 実 DELETE は u1 と u3 の 2 回。待機は u3 の直前 1 回のみ（u1 は初回、u2 はスキップ）
        self.assertEqual(sleep_mock.call_count, 1)
        sleep_mock.assert_called_once_with(2.0)

    def test_no_sleep_when_interval_zero(self) -> None:
        """interval=0（デフォルト）では time.sleep を呼ばない."""
        targets = [
            self._make_target("2026-05-01", edit_url="u1"),
            self._make_target("2026-05-02", edit_url="u2"),
        ]
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": "u2"},
        ])
        sleep_mock = MagicMock()
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena.time, "sleep", sleep_mock), \
             patch.object(delete_hatena, "_atompub_request", return_value=(204, b"")):
            delete_hatena.process_targets(
                targets, remote_only=True, local_only=False,
                hatena_id="u", api_key="k",
            )
        sleep_mock.assert_not_called()

    def test_local_only_does_not_sleep(self) -> None:
        """--local-only 相当（はてな DELETE なし）では interval を渡しても待機しない."""
        targets = [
            self._make_target("2026-05-01", edit_url="u1"),
            self._make_target("2026-05-02", edit_url="u2"),
        ]
        self._write_jsonl([
            {"date": "2026-05-01", "title": "t", "edit_url": "u1"},
            {"date": "2026-05-02", "title": "t", "edit_url": "u2"},
        ])
        sleep_mock = MagicMock()
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena.time, "sleep", sleep_mock), \
             patch.object(delete_hatena, "_atompub_request") as atompub_mock:
            delete_hatena.process_targets(
                targets, remote_only=False, local_only=True,
                hatena_id="u", api_key="k", interval=2.0,
            )
        atompub_mock.assert_not_called()
        sleep_mock.assert_not_called()


class JsonlRewriteErrorTest(unittest.TestCase):
    """rewrite_published_jsonl の OSError 捕捉と error_msg への組み込みをテスト."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.articles_dir = pathlib.Path(self.tmpdir.name) / "articles"
        self.articles_dir.mkdir()
        self.jsonl_path = self.articles_dir / "published.jsonl"

    def _make_target(self, date: str, *, edit_url: str | None) -> delete_hatena.Target:
        path = self.articles_dir / f"{date}-diary.md"
        path.write_text("dummy", encoding="utf-8")
        entry = {"date": date, "title": "t", "edit_url": edit_url}
        return delete_hatena.Target(
            date=date, article_path=path, title="t", entry=entry,
        )

    def test_success_path_oserror_returns_error_msg(self) -> None:
        """全件成功後の jsonl 書換が OSError の場合、終了コード 1 + エラーメッセージで返る."""
        target = self._make_target("2026-05-01", edit_url="u1")
        self.jsonl_path.write_text(
            json.dumps({"date": "2026-05-01", "title": "t", "edit_url": "u1"})
            + "\n",
            encoding="utf-8",
        )
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", return_value=(200, b"")), \
             patch.object(
                 delete_hatena, "rewrite_published_jsonl",
                 side_effect=OSError("disk full"),
             ):
            results, pending, error = delete_hatena.process_targets(
                [target], remote_only=False, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertIsNotNone(error)
        self.assertIn("jsonl 書き換え失敗", error)
        self.assertIn("disk full", error)

    def test_failure_path_oserror_appends_to_error_msg(self) -> None:
        """削除失敗 + jsonl 書換も失敗のケース、両方のエラーが error_msg に含まれる."""
        err = urllib.error.HTTPError(
            url="https://example.com/e/1",
            code=500,
            msg="Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        target = self._make_target("2026-05-01", edit_url="u1")
        with patch.object(delete_hatena, "PUBLISHED_JSONL", self.jsonl_path), \
             patch.object(delete_hatena, "REPO_ROOT", pathlib.Path(self.tmpdir.name)), \
             patch.object(delete_hatena, "_atompub_request", side_effect=err), \
             patch.object(
                 delete_hatena, "rewrite_published_jsonl",
                 side_effect=OSError("disk full"),
             ):
            results, pending, error = delete_hatena.process_targets(
                [target], remote_only=False, local_only=False,
                hatena_id="u", api_key="k",
            )
        self.assertIsNotNone(error)
        self.assertIn("500", error)
        self.assertIn("jsonl 書き換えも失敗", error)
        self.assertIn("disk full", error)


class MainExclusiveOptionsTest(unittest.TestCase):
    """main の排他オプション・引数バリデーション."""

    def test_remote_only_and_local_only_returns_error(self) -> None:
        rc = delete_hatena.main(["2026-05-01", "--remote-only", "--local-only"])
        self.assertEqual(rc, 1)

    def test_negative_interval_returns_error(self) -> None:
        rc = delete_hatena.main(["2026-05-01", "--interval", "-1"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
