"""publish_hatena.py の主要関数のユニットテスト.

仕様: aidlc-docs/plan-work/issue-42.md (テスト方針)

実行:

    python -m unittest tests.test_publish_hatena
"""
from __future__ import annotations

import json
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
        self._touch("2026-05-13-diary.md")
        result = publish_hatena.select_article(None)
        self.assertEqual(result.name, "2026-05-13-diary.md")

    def test_latest_by_filename(self) -> None:
        # ファイル名昇順で最新を返す（1 日 1 記事前提のため日付で順序が決まる）
        self._touch("2026-05-12-diary.md")
        self._touch("2026-05-13-diary.md")
        result = publish_hatena.select_article(None)
        self.assertEqual(result.name, "2026-05-13-diary.md")

    def test_date_prefix_filter(self) -> None:
        # date 指定時は前方一致で絞り込む（1 日 1 記事前提）
        self._touch("2026-05-12-diary.md")
        self._touch("2026-05-13-diary.md")
        result = publish_hatena.select_article("2026-05-12")
        self.assertEqual(result.name, "2026-05-12-diary.md")

    def test_no_articles_raises(self) -> None:
        self._touch("README.md")  # 日付プレフィックスなしのみ
        with self.assertRaises(SystemExit):
            publish_hatena.select_article(None)


class LookupPublishedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.published_path = pathlib.Path(self.tmpdir.name) / "published.jsonl"
        # publish_hatena は module-level の PUBLISHED_JSONL を参照する
        self._orig = publish_hatena.PUBLISHED_JSONL
        publish_hatena.PUBLISHED_JSONL = self.published_path
        self.addCleanup(
            lambda: setattr(publish_hatena, "PUBLISHED_JSONL", self._orig)
        )

    def test_no_file_returns_none(self) -> None:
        self.assertIsNone(publish_hatena.lookup_published("2026-05-13"))

    def test_entry_without_edit_url(self) -> None:
        self.published_path.write_text(
            '{"date": "2026-05-12", "title": "edit_url 未保存の記事", "edit_url": null}\n',
            encoding="utf-8",
        )
        entry = publish_hatena.lookup_published("2026-05-12")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["date"], "2026-05-12")
        self.assertEqual(entry["title"], "edit_url 未保存の記事")
        self.assertIsNone(entry["edit_url"])

    def test_entry_with_edit_url(self) -> None:
        self.published_path.write_text(
            '{"date": "2026-05-13", "title": "edit_url 保存済みの記事",'
            ' "edit_url": "https://example.com/atom/entry/1"}\n',
            encoding="utf-8",
        )
        entry = publish_hatena.lookup_published("2026-05-13")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["title"], "edit_url 保存済みの記事")
        self.assertEqual(entry["edit_url"], "https://example.com/atom/entry/1")

    def test_title_with_special_chars_is_preserved(self) -> None:
        # JSON エスケープを通して特殊文字を含むタイトルが復元できる
        self.published_path.write_text(
            '{"date": "2026-05-13", "title": "装飾 | や \\"記号\\" を含むタイトル",'
            ' "edit_url": "https://example.com/x"}\n',
            encoding="utf-8",
        )
        entry = publish_hatena.lookup_published("2026-05-13")
        self.assertEqual(entry["title"], '装飾 | や "記号" を含むタイトル')
        self.assertEqual(entry["edit_url"], "https://example.com/x")

    def test_non_matching_date_returns_none(self) -> None:
        self.published_path.write_text(
            '{"date": "2026-05-12", "title": "別日付", "edit_url": null}\n',
            encoding="utf-8",
        )
        self.assertIsNone(publish_hatena.lookup_published("2026-05-13"))

    def test_malformed_json_line_is_skipped(self) -> None:
        # JSON パース失敗行はスキップして後続を読む
        self.published_path.write_text(
            "not json at all\n"
            '{"date": "2026-05-13", "title": "正常エントリ", "edit_url": null}\n',
            encoding="utf-8",
        )
        entry = publish_hatena.lookup_published("2026-05-13")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["title"], "正常エントリ")

    def test_missing_required_keys_are_skipped(self) -> None:
        # date or title が欠落した行はスキップ
        self.published_path.write_text(
            '{"title": "date 欠落", "edit_url": null}\n'
            '{"date": "2026-05-13", "edit_url": null}\n',
            encoding="utf-8",
        )
        self.assertIsNone(publish_hatena.lookup_published("2026-05-13"))


class UpdatePublishedTitleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.published_path = pathlib.Path(self.tmpdir.name) / "published.jsonl"
        self._orig = publish_hatena.PUBLISHED_JSONL
        publish_hatena.PUBLISHED_JSONL = self.published_path
        self.addCleanup(
            lambda: setattr(publish_hatena, "PUBLISHED_JSONL", self._orig)
        )

    def test_no_file_returns_false(self) -> None:
        # published.jsonl が存在しない場合は False
        result = publish_hatena.update_published_title("2026-05-13", "新タイトル")
        self.assertFalse(result)

    def test_matching_date_updates_title_and_keeps_edit_url(self) -> None:
        # 対象日付の title が更新され、edit_url は保持される
        self.published_path.write_text(
            '{"date": "2026-05-13", "title": "旧タイトル", "edit_url": "https://example.com/atom/entry/1"}\n',
            encoding="utf-8",
        )
        result = publish_hatena.update_published_title("2026-05-13", "新タイトル")
        self.assertTrue(result)
        content = self.published_path.read_text(encoding="utf-8")
        obj = json.loads(content.strip())
        self.assertEqual(obj["title"], "新タイトル")
        self.assertEqual(obj["edit_url"], "https://example.com/atom/entry/1")
        self.assertEqual(obj["date"], "2026-05-13")

    def test_non_matching_date_returns_false_and_keeps_file(self) -> None:
        # 対象日付がない場合は False、ファイル内容は保持される
        original = '{"date": "2026-05-12", "title": "別日付", "edit_url": null}\n'
        self.published_path.write_text(original, encoding="utf-8")
        result = publish_hatena.update_published_title("2026-05-13", "新タイトル")
        self.assertFalse(result)
        self.assertEqual(self.published_path.read_text(encoding="utf-8"), original)

    def test_only_matching_row_is_updated(self) -> None:
        # 複数行のうち対象日付の行だけが更新され、他行は変更なし
        self.published_path.write_text(
            '{"date": "2026-05-11", "title": "11 日", "edit_url": "https://example.com/11"}\n'
            '{"date": "2026-05-12", "title": "旧 12 日", "edit_url": "https://example.com/12"}\n'
            '{"date": "2026-05-13", "title": "13 日", "edit_url": "https://example.com/13"}\n',
            encoding="utf-8",
        )
        result = publish_hatena.update_published_title("2026-05-12", "新 12 日")
        self.assertTrue(result)
        lines = self.published_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["title"], "11 日")
        self.assertEqual(json.loads(lines[1])["title"], "新 12 日")
        self.assertEqual(json.loads(lines[1])["edit_url"], "https://example.com/12")
        self.assertEqual(json.loads(lines[2])["title"], "13 日")

    def test_malformed_and_blank_lines_preserved(self) -> None:
        # 壊れた JSON 行・空行は変更されず保持される
        self.published_path.write_text(
            "not json at all\n"
            "\n"
            '{"date": "2026-05-13", "title": "旧", "edit_url": null}\n'
            "\n",
            encoding="utf-8",
        )
        result = publish_hatena.update_published_title("2026-05-13", "新")
        self.assertTrue(result)
        content = self.published_path.read_text(encoding="utf-8")
        # 壊れた行と空行が原型のまま残ること
        self.assertIn("not json at all", content)
        # 対象行が更新されること
        for line in content.split("\n"):
            if line.strip() and line.startswith("{"):
                try:
                    obj = json.loads(line)
                    if obj.get("date") == "2026-05-13":
                        self.assertEqual(obj["title"], "新")
                except json.JSONDecodeError:
                    pass


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

    def test_draft_none_omits_app_control(self) -> None:
        payload = publish_hatena.build_atom_entry(
            title="t", body="b", category=None, draft=None
        )
        root = ET.fromstring(payload)
        self.assertIsNone(root.find("app:control", self.NS))
        self.assertIsNone(root.find("app:control/app:draft", self.NS))


class BasicAuthHeaderTest(unittest.TestCase):
    def test_format(self) -> None:
        # Aladdin:open sesame の RFC 7617 例（決定論的）
        header = publish_hatena.basic_auth_header("Aladdin", "open sesame")
        self.assertEqual(header, "Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==")


class AppendPublishedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.published_path = pathlib.Path(self.tmpdir.name) / "published.jsonl"
        self._orig = publish_hatena.PUBLISHED_JSONL
        publish_hatena.PUBLISHED_JSONL = self.published_path
        self.addCleanup(
            lambda: setattr(publish_hatena, "PUBLISHED_JSONL", self._orig)
        )

    def test_appends_with_edit_url(self) -> None:
        publish_hatena.append_published(
            "2026-05-13", "テスト記事", "https://example.com/atom/entry/1"
        )
        text = self.published_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            '{"date": "2026-05-13", "title": "テスト記事",'
            ' "edit_url": "https://example.com/atom/entry/1"}\n',
        )

    def test_appends_with_null_edit_url(self) -> None:
        publish_hatena.append_published("2026-05-13", "テスト記事", None)
        text = self.published_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            '{"date": "2026-05-13", "title": "テスト記事", "edit_url": null}\n',
        )

    def test_appends_to_existing(self) -> None:
        existing = (
            '{"date": "2026-05-12", "title": "既存", "edit_url": null}\n'
        )
        self.published_path.write_text(existing, encoding="utf-8")
        publish_hatena.append_published(
            "2026-05-13", "テスト記事", "https://example.com/atom/entry/1"
        )
        text = self.published_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            existing
            + '{"date": "2026-05-13", "title": "テスト記事",'
            ' "edit_url": "https://example.com/atom/entry/1"}\n',
        )

    def test_appends_preserves_non_ascii(self) -> None:
        # ensure_ascii=False により日本語が \\uXXXX エスケープされない
        publish_hatena.append_published("2026-05-13", "ひらがな", None)
        text = self.published_path.read_text(encoding="utf-8")
        self.assertIn("ひらがな", text)
        self.assertNotIn("\\u3072", text)


class ExtractLinkHrefTest(unittest.TestCase):
    RESPONSE = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<entry xmlns="http://www.w3.org/2005/Atom">\n'
        '  <id>tag:blog.hatena.ne.jp,2013:blog-foo-bar-baz-entry-123</id>\n'
        '  <link rel="alternate" type="text/html" href="https://example.hatenablog.com/entry/123"/>\n'
        '  <link rel="edit" href="https://blog.hatena.ne.jp/foo/bar/atom/entry/123"/>\n'
        '</entry>\n'
    )

    def test_alternate_returns_public_url(self) -> None:
        href = publish_hatena.extract_link_href(self.RESPONSE, rel="alternate")
        self.assertEqual(href, "https://example.hatenablog.com/entry/123")

    def test_edit_returns_atompub_url(self) -> None:
        href = publish_hatena.extract_link_href(self.RESPONSE, rel="edit")
        self.assertEqual(
            href, "https://blog.hatena.ne.jp/foo/bar/atom/entry/123"
        )

    def test_unknown_rel_returns_none(self) -> None:
        self.assertIsNone(
            publish_hatena.extract_link_href(self.RESPONSE, rel="self")
        )

    def test_invalid_xml_returns_none(self) -> None:
        self.assertIsNone(
            publish_hatena.extract_link_href("not xml at all", rel="edit")
        )


if __name__ == "__main__":
    unittest.main()
