"""convert_article_html.py のユニットテスト.

仕様: .claude/skills/write-hatena-diary/balloon-html.md
計画: aidlc-docs/plan-work/issue-47.md (テスト方針)

実行:

    python -m unittest tests.test_convert_article_html
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import convert_article_html  # noqa: E402


class BalloonConvertTest(unittest.TestCase):
    def test_left_balloon_basic(self) -> None:
        src = ":::kuro-chan\nぼく、ちょっと相談があるんですが。\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="balloon balloon-l"><div class="icon"></div>'
            '<div class="text">ぼく、ちょっと相談があるんですが。</div></div>',
            out,
        )

    def test_right_balloon_basic(self) -> None:
        src = ":::nee-san\nあら、どうしたの。\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="balloon balloon-r"><div class="icon"></div>'
            '<div class="text">あら、どうしたの。</div></div>',
            out,
        )

    def test_balloon_multiline_body_is_joined_with_space(self) -> None:
        src = ":::kuro-chan\n1 行目\n2 行目\n3 行目\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">1 行目 2 行目 3 行目</div>',
            out,
        )

    def test_balloon_inline_html_passes_through(self) -> None:
        src = ":::kuro-chan\n<code>agent-commons</code> のルール改修をしてて\n:::\n"
        out = convert_article_html.convert(src)
        # body は HTML 直書きとして扱うため、エスケープされずに残る
        self.assertIn(
            '<div class="text"><code>agent-commons</code> のルール改修をしてて</div>',
            out,
        )

    def test_balloon_sequence_lr(self) -> None:
        src = ":::kuro-chan\nA\n:::\n:::nee-san\nB\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn('class="balloon balloon-l"', out)
        self.assertIn('class="balloon balloon-r"', out)
        self.assertIn(">A<", out)
        self.assertIn(">B<", out)

    def test_non_balloon_lines_pass_through(self) -> None:
        src = "## 見出し\n\n通常段落です。\n\n:::kuro-chan\nセリフ\n:::\n\n別の段落。\n"
        out = convert_article_html.convert(src)
        self.assertIn("## 見出し", out)
        self.assertIn("通常段落です。", out)
        self.assertIn("別の段落。", out)
        self.assertIn('class="balloon balloon-l"', out)

    def test_unclosed_balloon_raises(self) -> None:
        src = ":::kuro-chan\nセリフ\n本文最後まで閉じない\n"
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(src)

    def test_nested_balloon_raises(self) -> None:
        src = ":::kuro-chan\nセリフ\n:::nee-san\n入れ子\n:::\n:::\n"
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(src)

    def test_balloon_inline_backtick_is_auto_converted_to_code(self) -> None:
        # balloon 内で `name` を使うと変換時に <code>name</code> に自動置換される。
        # 書き手は balloon の内外を問わず通常の backtick で書ける。
        src = ":::kuro-chan\n`agent-commons` のルール改修をしてて\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><code>agent-commons</code> のルール改修をしてて</div>',
            out,
        )
        # 素の backtick は変換後の出力に残らない
        self.assertNotIn(
            '<div class="text">`agent-commons`',
            out,
        )

    def test_balloon_multiple_inline_backticks_all_converted(self) -> None:
        # 1 つのバルーン内に複数の backtick がある場合、すべて <code> 化される。
        src = ":::kuro-chan\n`agent-commons` で `invariants.md` を直しました\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<code>agent-commons</code> で <code>invariants.md</code>',
            out,
        )

    def test_balloon_code_tag_is_allowed(self) -> None:
        # <code> タグ直書きも引き続きサポート（HTML 直書きの性質を保つ）。
        src = ":::kuro-chan\n<code>agent-commons</code> のルール改修をしてて\n:::\n"
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><code>agent-commons</code> のルール改修をしてて</div>',
            out,
        )


class BlueskyConvertTest(unittest.TestCase):
    def _basic_block(self, *, text: str = "投稿本文") -> str:
        return (
            ":::bluesky\n"
            "did=did:plc:abcdef\n"
            "cid=bafyabcdef\n"
            "rkey=3lmnopqr\n"
            "handle=example.bsky.social\n"
            "display-name=表示名\n"
            "created-at=2026-05-14T01:33:34.400Z\n"
            "lang=ja\n"
            f"text={text}\n"
            ":::\n"
        )

    def test_bluesky_basic(self) -> None:
        out = convert_article_html.convert(self._basic_block())
        self.assertIn(
            'class="bluesky-embed" data-bluesky-uri='
            '"at://did:plc:abcdef/app.bsky.feed.post/3lmnopqr"',
            out,
        )
        self.assertIn('data-bluesky-cid="bafyabcdef"', out)
        self.assertIn('<p lang="ja">投稿本文</p>', out)
        self.assertIn(
            'href="https://bsky.app/profile/did:plc:abcdef?ref_src=embed"',
            out,
        )
        self.assertIn("表示名 (@example.bsky.social)", out)
        self.assertIn(
            'href="https://bsky.app/profile/example.bsky.social/post/3lmnopqr"',
            out,
        )
        self.assertIn("https://embed.bsky.app/static/embed.js", out)

    def test_bluesky_lang_default_to_ja(self) -> None:
        # lang を含めない
        block = (
            ":::bluesky\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
            ":::\n"
        )
        out = convert_article_html.convert(block)
        self.assertIn('<p lang="ja">hi</p>', out)

    def test_bluesky_text_is_html_escaped(self) -> None:
        out = convert_article_html.convert(self._basic_block(text="<script>alert(1)</script>"))
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)

    def test_bluesky_text_multiline(self) -> None:
        block = (
            ":::bluesky\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=1 行目\n"
            "2 行目\n"
            "3 行目\n"
            ":::\n"
        )
        out = convert_article_html.convert(block)
        # 改行を含む値が HTML エスケープされてそのまま入る
        self.assertIn("1 行目\n2 行目\n3 行目", out)

    def test_bluesky_full_width_colon_in_did_is_normalized(self) -> None:
        block = (
            ":::bluesky\n"
            "did=did：plc：abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
            ":::\n"
        )
        out = convert_article_html.convert(block)
        self.assertIn("did:plc:abc", out)
        self.assertNotIn("did：plc：abc", out)

    def test_bluesky_missing_required_key_raises(self) -> None:
        block = (
            ":::bluesky\n"
            "did=did:plc:abc\n"
            # cid 欠落
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
            ":::\n"
        )
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_unknown_key_raises(self) -> None:
        block = (
            ":::bluesky\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "extra=おかしなキー\n"
            "text=hi\n"
            ":::\n"
        )
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_unclosed_raises(self) -> None:
        block = (
            ":::bluesky\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
        )  # 閉じ ::: なし
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)


class MixedConvertTest(unittest.TestCase):
    def test_balloon_and_bluesky_coexist(self) -> None:
        src = (
            ":::kuro-chan\nセリフ\n:::\n"
            "\n"
            ":::bluesky\n"
            "did=did:plc:a\n"
            "cid=bafya\n"
            "rkey=3a\n"
            "handle=h.bsky.social\n"
            "display-name=n\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=t\n"
            ":::\n"
            "\n"
            ":::nee-san\nおっけー\n:::\n"
        )
        out = convert_article_html.convert(src)
        self.assertIn('class="balloon balloon-l"', out)
        self.assertIn('class="balloon balloon-r"', out)
        self.assertIn('class="bluesky-embed"', out)

    def test_passthrough_when_no_blocks(self) -> None:
        src = "通常記事\n\n## 見出し\n\n本文。\n"
        out = convert_article_html.convert(src)
        self.assertEqual(src, out)


if __name__ == "__main__":
    unittest.main()
