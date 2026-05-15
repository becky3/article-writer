"""publish_hatena.py の主要関数のユニットテスト.

仕様: aidlc-docs/plan-work/issue-42.md (テスト方針)

実行:

    python -m unittest tests.test_publish_hatena
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

# scripts/ を import path に追加
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import publish_hatena  # noqa: E402


class ParseArticleTest(unittest.TestCase):
    def _write(self, content: str) -> pathlib.Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        )
        tmp.write(content)
        tmp.close()
        path = pathlib.Path(tmp.name)
        self.addCleanup(path.unlink)
        return path

    def test_frontmatter_and_body_are_separated(self) -> None:
        path = self._write(
            '---\n'
            'title: "テスト記事"\n'
            'date: "2026-05-13"\n'
            'category: "diary"\n'
            '---\n'
            '\n'
            '# テスト記事\n'
            '\n'
            '本文です。\n'
        )
        fm, body = publish_hatena.parse_article(path)
        self.assertEqual(fm["title"], "テスト記事")
        self.assertEqual(fm["date"], "2026-05-13")
        self.assertEqual(fm["category"], "diary")
        self.assertIn("# テスト記事", body)
        self.assertIn("本文です。", body)

    def test_missing_frontmatter_raises(self) -> None:
        path = self._write("# 本文のみ\n")
        with self.assertRaises(SystemExit):
            publish_hatena.parse_article(path)

    def test_missing_required_field_raises(self) -> None:
        path = self._write(
            '---\n'
            'category: "diary"\n'
            '---\n'
            '\n'
            '本文\n'
        )
        with self.assertRaises(SystemExit):
            publish_hatena.parse_article(path)

    def test_unparsable_date_is_kept_as_is(self) -> None:
        # parse_article 自体は date の形式検証をしない（main 側で実施）。
        # ここでは値がそのまま frontmatter に保持されることを確認する。
        path = self._write(
            '---\n'
            'title: "テスト"\n'
            'date: "2026/5/13"\n'
            '---\n'
            '\n'
            '本文\n'
        )
        fm, _ = publish_hatena.parse_article(path)
        self.assertEqual(fm["date"], "2026/5/13")


class StripLeadingH1Test(unittest.TestCase):
    def test_matching_h1_is_stripped(self) -> None:
        body = "# テスト記事\n\n本文です。\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, "本文です。\n")

    def test_non_matching_h1_kept(self) -> None:
        body = "# 別のタイトル\n\n本文です。\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, body)

    def test_no_h1_kept(self) -> None:
        body = "本文のみで始まる記事\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, body)

    def test_leading_blank_lines_skipped(self) -> None:
        body = "\n\n# テスト記事\n\n本文\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, "本文\n")

    def test_h2_not_stripped(self) -> None:
        # `## テスト記事` は H1 ではない
        body = "## テスト記事\n\n本文\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, body)

    def test_double_hash_not_stripped(self) -> None:
        # `# # テスト記事` は H1 + 文字としての # で、H1 タイトルは "# テスト記事"
        # title="テスト記事" とは一致しないのでそのまま残る
        body = "# # テスト記事\n\n本文\n"
        result = publish_hatena.strip_leading_h1(body, "テスト記事")
        self.assertEqual(result, body)


class LoadEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.env_path = pathlib.Path(self.tmpdir.name) / ".env"
        self._orig = publish_hatena.ENV_FILE
        publish_hatena.ENV_FILE = self.env_path
        self.addCleanup(lambda: setattr(publish_hatena, "ENV_FILE", self._orig))

    def test_inline_comment_stripped(self) -> None:
        # 非クォート値は `#` 以降をコメントとして切り落とす
        self.env_path.write_text(
            "HATENA_ID=becky_example # owner's hatena id\n",
            encoding="utf-8",
        )
        env = publish_hatena.load_env()
        self.assertEqual(env["HATENA_ID"], "becky_example")

    def test_quoted_value_preserves_hash(self) -> None:
        # クォート内の `#` は値として保持される
        self.env_path.write_text(
            'HATENA_BLOG_ID="example.com#test"\n', encoding="utf-8"
        )
        env = publish_hatena.load_env()
        self.assertEqual(env["HATENA_BLOG_ID"], "example.com#test")

    def test_comment_only_line_skipped(self) -> None:
        # 行頭 `#` のコメント行はスキップされる
        self.env_path.write_text(
            "# this is a comment\nHATENA_ID=alice\n", encoding="utf-8"
        )
        env = publish_hatena.load_env()
        self.assertEqual(env["HATENA_ID"], "alice")
        self.assertNotIn("# this is a comment", env)


class SelectArticleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.articles_dir = pathlib.Path(self.tmpdir.name) / "articles"
        self.articles_dir.mkdir()
        self._orig = publish_hatena.ARTICLES_DIR
        publish_hatena.ARTICLES_DIR = self.articles_dir
        self.addCleanup(
            lambda: setattr(publish_hatena, "ARTICLES_DIR", self._orig)
        )

    def _touch(self, name: str) -> None:
        (self.articles_dir / name).write_text("dummy\n", encoding="utf-8")

    def test_non_dated_files_excluded(self) -> None:
        # README.md 等の日付プレフィックスを持たないファイルは候補に含めない
        self._touch("README.md")
        self._touch("2026-05-13-09-00-00-foo.md")
        result = publish_hatena.select_article(None)
        self.assertEqual(result.name, "2026-05-13-09-00-00-foo.md")

    def test_latest_by_filename(self) -> None:
        # ファイル名昇順で最新を返す
        self._touch("2026-05-12-08-00-00-old.md")
        self._touch("2026-05-13-09-00-00-new.md")
        result = publish_hatena.select_article(None)
        self.assertEqual(result.name, "2026-05-13-09-00-00-new.md")

    def test_date_prefix_filter(self) -> None:
        # date 指定時は前方一致で絞り込む
        self._touch("2026-05-12-08-00-00-old.md")
        self._touch("2026-05-13-09-00-00-new.md")
        result = publish_hatena.select_article("2026-05-12")
        self.assertEqual(result.name, "2026-05-12-08-00-00-old.md")

    def test_no_articles_raises(self) -> None:
        self._touch("README.md")  # 日付プレフィックスなしのみ
        with self.assertRaises(SystemExit):
            publish_hatena.select_article(None)


class CheckDuplicateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.published_path = pathlib.Path(self.tmpdir.name) / "published.txt"
        # publish_hatena は module-level の PUBLISHED_TXT を参照する
        self._orig = publish_hatena.PUBLISHED_TXT
        publish_hatena.PUBLISHED_TXT = self.published_path
        self.addCleanup(lambda: setattr(publish_hatena, "PUBLISHED_TXT", self._orig))

    def test_no_file_returns_false(self) -> None:
        self.assertFalse(publish_hatena.check_duplicate("2026-05-13"))

    def test_matching_date_returns_true(self) -> None:
        self.published_path.write_text(
            "# comment\n- (2026-05-12) 既存記事\n- (2026-05-13) 別の記事\n",
            encoding="utf-8",
        )
        self.assertTrue(publish_hatena.check_duplicate("2026-05-13"))

    def test_non_matching_date_returns_false(self) -> None:
        self.published_path.write_text(
            "- (2026-05-12) 既存記事\n", encoding="utf-8"
        )
        self.assertFalse(publish_hatena.check_duplicate("2026-05-13"))

    def test_commented_date_is_ignored(self) -> None:
        # '# - (2026-05-13) ...' のようなコメント行は重複扱いしない
        self.published_path.write_text(
            "# - (2026-05-13) 例示行\n", encoding="utf-8"
        )
        self.assertFalse(publish_hatena.check_duplicate("2026-05-13"))


class BuildAtomEntryTest(unittest.TestCase):
    NS = {
        "atom": "http://www.w3.org/2005/Atom",
        "app": "http://www.w3.org/2007/app",
    }

    def test_required_elements_present(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="タイトル",
            body="**Markdown** 本文",
            category="diary",
            draft=True,
        )
        text = payload.decode("utf-8")
        self.assertTrue(text.startswith("<?xml"))
        root = ET.fromstring(payload)
        self.assertEqual(root.tag, "{http://www.w3.org/2005/Atom}entry")
        self.assertEqual(root.find("atom:title", self.NS).text, "タイトル")
        content = root.find("atom:content", self.NS)
        self.assertEqual(content.get("type"), "text/x-markdown")
        self.assertEqual(content.text, "**Markdown** 本文")
        category = root.find("atom:category", self.NS)
        self.assertEqual(category.get("term"), "diary")
        draft = root.find("app:control/app:draft", self.NS)
        self.assertEqual(draft.text, "yes")

    def test_draft_false_emits_no(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="t", body="b", category=None, draft=False
        )
        root = ET.fromstring(payload)
        draft = root.find("app:control/app:draft", self.NS)
        self.assertEqual(draft.text, "no")

    def test_category_omitted(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="t", body="b", category=None, draft=True
        )
        root = ET.fromstring(payload)
        self.assertIsNone(root.find("atom:category", self.NS))

    def test_published_iso_emits_updated(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="t",
            body="b",
            category=None,
            draft=True,
            published_iso="2026-04-30T00:00:00+09:00",
        )
        root = ET.fromstring(payload)
        updated = root.find("atom:updated", self.NS)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.text, "2026-04-30T00:00:00+09:00")

    def test_published_iso_omitted_when_none(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="t", body="b", category=None, draft=True
        )
        root = ET.fromstring(payload)
        self.assertIsNone(root.find("atom:updated", self.NS))


class BasicAuthHeaderTest(unittest.TestCase):
    def test_format(self) -> None:
        # Aladdin:open sesame の RFC 7617 例（決定論的）
        header = publish_hatena.basic_auth_header("Aladdin", "open sesame")
        self.assertEqual(header, "Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==")


class AppendPublishedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.published_path = pathlib.Path(self.tmpdir.name) / "published.txt"
        self._orig = publish_hatena.PUBLISHED_TXT
        publish_hatena.PUBLISHED_TXT = self.published_path
        self.addCleanup(lambda: setattr(publish_hatena, "PUBLISHED_TXT", self._orig))

    def test_appends_line_in_expected_format(self) -> None:
        publish_hatena.append_published("2026-05-13", "テスト記事")
        text = self.published_path.read_text(encoding="utf-8")
        self.assertEqual(text, "- (2026-05-13) テスト記事\n")

    def test_appends_to_existing(self) -> None:
        self.published_path.write_text(
            "# comment\n", encoding="utf-8"
        )
        publish_hatena.append_published("2026-05-13", "テスト記事")
        text = self.published_path.read_text(encoding="utf-8")
        self.assertEqual(
            text, "# comment\n- (2026-05-13) テスト記事\n"
        )


if __name__ == "__main__":
    unittest.main()
