"""convert_article_html.py のユニットテスト.

仕様: .claude/skills/write-hatena-diary/balloon-html.md
計画: aidlc-docs/plan-work/issue-60.md (テスト方針)

実行:

    python -m unittest tests.test_convert_article_html
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import article_syntax  # noqa: E402
import convert_article_html  # noqa: E402
from article_syntax import (  # noqa: E402
    BALLOON_MARKER_SUFFIX,
    BLUESKY_CLOSE_TOKEN,
    BLUESKY_OPEN_TOKEN,
)


def _balloon(name: str, body: str) -> str:
    """balloon 単行マーカー記法の入力を組み立てる."""
    return f"{name}{BALLOON_MARKER_SUFFIX}{body}\n"


def _bluesky(fields: dict[str, str]) -> str:
    """bluesky フェンス記法の入力を組み立てる. fields の挿入順がそのまま出力順になる."""
    lines = [BLUESKY_OPEN_TOKEN]
    lines.extend(f"{k}={v}" for k, v in fields.items())
    lines.append(BLUESKY_CLOSE_TOKEN)
    return "\n".join(lines) + "\n"


class BalloonConvertTest(unittest.TestCase):
    def test_left_balloon_basic(self) -> None:
        src = _balloon("kuro-chan", "ぼく、ちょっと相談があるんですが。")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="balloon balloon-l"><div class="icon"></div>'
            '<div class="text">ぼく、ちょっと相談があるんですが。</div></div>',
            out,
        )

    def test_right_balloon_basic(self) -> None:
        src = _balloon("nee-san", "あら、どうしたの。")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="balloon balloon-r"><div class="icon"></div>'
            '<div class="text">あら、どうしたの。</div></div>',
            out,
        )

    def test_balloon_marker_with_space_after_is_trimmed(self) -> None:
        # マーカー直後の半角スペースは任意。空白あり/なし両方が同じ HTML を生成する。
        src_no_space = _balloon("kuro-chan", "メッセージ")
        src_with_space = f"kuro-chan{BALLOON_MARKER_SUFFIX} メッセージ\n"
        src_with_many_spaces = f"kuro-chan{BALLOON_MARKER_SUFFIX}   メッセージ\n"
        out_no = convert_article_html.convert(src_no_space)
        out_with = convert_article_html.convert(src_with_space)
        out_many = convert_article_html.convert(src_with_many_spaces)
        self.assertEqual(out_no, out_with)
        self.assertEqual(out_no, out_many)

    def test_balloon_br_passes_through_for_pseudo_linebreak(self) -> None:
        # 1 行 1 セリフ規約。長文の疑似改行は <br/> 直書きで実現する。
        # HTML 直書きはエスケープされず通過する。
        src = _balloon("nee-san", "1 段落目の内容。<br/>2 段落目の内容。")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">1 段落目の内容。<br/>2 段落目の内容。</div>',
            out,
        )

    def test_balloon_inline_html_passes_through(self) -> None:
        src = _balloon("kuro-chan", "<code>agent-commons</code> のルール改修をしてて")
        out = convert_article_html.convert(src)
        # body は HTML 直書きとして扱うため、エスケープされずに残る
        self.assertIn(
            '<div class="text"><code>agent-commons</code> のルール改修をしてて</div>',
            out,
        )

    def test_balloon_sequence_lr(self) -> None:
        src = _balloon("kuro-chan", "A") + _balloon("nee-san", "B")
        out = convert_article_html.convert(src)
        self.assertIn('class="balloon balloon-l"', out)
        self.assertIn('class="balloon balloon-r"', out)
        self.assertIn(">A<", out)
        self.assertIn(">B<", out)

    def test_non_balloon_lines_pass_through(self) -> None:
        src = (
            "## 見出し\n\n通常段落です。\n\n"
            + _balloon("kuro-chan", "セリフ")
            + "\n別の段落。\n"
        )
        out = convert_article_html.convert(src)
        self.assertIn("## 見出し", out)
        self.assertIn("通常段落です。", out)
        self.assertIn("別の段落。", out)
        self.assertIn('class="balloon balloon-l"', out)

    def test_balloon_inline_backtick_is_auto_converted_to_code(self) -> None:
        # balloon 内で `name` を使うと変換時に <code>name</code> に自動置換される。
        # 書き手は balloon の内外を問わず通常の backtick で書ける。
        src = _balloon("kuro-chan", "`agent-commons` のルール改修をしてて")
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
        src = _balloon("kuro-chan", "`agent-commons` で `invariants.md` を直しました")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<code>agent-commons</code> で <code>invariants.md</code>',
            out,
        )

    def test_balloon_code_tag_is_allowed(self) -> None:
        # <code> タグ直書きも引き続きサポート（HTML 直書きの性質を保つ）。
        src = _balloon("kuro-chan", "<code>agent-commons</code> のルール改修をしてて")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><code>agent-commons</code> のルール改修をしてて</div>',
            out,
        )

    def test_balloon_bold_is_converted_to_strong(self) -> None:
        # **foo** が <strong>foo</strong> に自動置換される。
        src = _balloon("kuro-chan", "これは **重要** な話です")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">これは <strong>重要</strong> な話です</div>',
            out,
        )

    def test_balloon_italic_is_converted_to_em(self) -> None:
        # *foo* が <em>foo</em> に自動置換される。
        src = _balloon("kuro-chan", "これは *強調* された言葉")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">これは <em>強調</em> された言葉</div>',
            out,
        )

    def test_balloon_strikethrough_is_converted_to_del(self) -> None:
        # ~~foo~~ が <del>foo</del> に自動置換される。
        src = _balloon("kuro-chan", "もう ~~古い~~ 話")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">もう <del>古い</del> 話</div>',
            out,
        )

    def test_balloon_bold_takes_priority_over_italic(self) -> None:
        # **foo** が *foo* として italic 誤マッチしないこと。
        src = _balloon("kuro-chan", "**太字** のみ")
        out = convert_article_html.convert(src)
        self.assertIn("<strong>太字</strong>", out)
        self.assertNotIn("<em>", out)

    def test_balloon_decorations_not_applied_inside_code(self) -> None:
        # <code> 内部の **foo** は装飾置換されず、リテラルのまま残る
        # （backtick 自動変換 → code プレースホルダー退避 → 装飾置換の順）。
        src = _balloon("kuro-chan", "`**not bold**` のままで残す")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><code>**not bold**</code> のままで残す</div>',
            out,
        )
        self.assertNotIn("<strong>", out)

    def test_balloon_decoration_and_code_coexist(self) -> None:
        # 装飾と code が混在しても、それぞれ独立に変換される。
        src = _balloon("kuro-chan", "**強調** と `code` を併用")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><strong>強調</strong> と <code>code</code> を併用</div>',
            out,
        )

    def test_balloon_multiple_bold_in_one_balloon(self) -> None:
        # 1 つの balloon 内に複数の **bold** がある場合、すべて <strong> 化される。
        src = _balloon("kuro-chan", "**A** と **B** が両方")
        out = convert_article_html.convert(src)
        self.assertIn("<strong>A</strong> と <strong>B</strong>", out)

    def test_balloon_single_asterisk_with_surrounding_space_is_literal(self) -> None:
        # 地の文の単独 `*`（前後空白）は装飾として誤発火せずリテラルのまま残る。
        src = _balloon("kuro-chan", "計算: 2 * 3 = 6 と 4 * 5 = 20")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">計算: 2 * 3 = 6 と 4 * 5 = 20</div>',
            out,
        )
        self.assertNotIn("<em>", out)

    def test_balloon_double_asterisk_with_surrounding_space_is_literal(self) -> None:
        # 地の文の単独 `**`（前後空白）も bold として誤発火しない。
        src = _balloon("kuro-chan", "計算: 2 ** 3 = 8")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">計算: 2 ** 3 = 8</div>',
            out,
        )
        self.assertNotIn("<strong>", out)

    def test_balloon_tilde_with_surrounding_space_is_literal(self) -> None:
        # 地の文の単独 `~~`（前後空白）も strike として誤発火しない。
        src = _balloon("kuro-chan", "波線 ~~ 単体は残す")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text">波線 ~~ 単体は残す</div>',
            out,
        )
        self.assertNotIn("<del>", out)

    def test_balloon_decoration_inner_whitespace_not_matched(self) -> None:
        # 内側が空白で始まる/終わる `* foo*` / `*foo *` は装飾としてマッチしない。
        src = _balloon("kuro-chan", "left * foo* と right *foo * は装飾にならない")
        out = convert_article_html.convert(src)
        self.assertNotIn("<em>", out)
        self.assertIn(
            '<div class="text">left * foo* と right *foo * は装飾にならない</div>',
            out,
        )

    def test_balloon_single_char_decoration_matches(self) -> None:
        # 1 文字の装飾（`*a*` `**b**` `~~c~~`）は内側が非空白 1 文字としてマッチする。
        src = _balloon("kuro-chan", "*a* と **b** と ~~c~~")
        out = convert_article_html.convert(src)
        self.assertIn("<em>a</em>", out)
        self.assertIn("<strong>b</strong>", out)
        self.assertIn("<del>c</del>", out)

    def test_balloon_bolditalic_triple_asterisk_is_converted(self) -> None:
        # ***foo*** が <strong><em>foo</em></strong> に変換される（タグ順序が正しい）。
        src = _balloon("kuro-chan", "***超重要*** な指摘")
        out = convert_article_html.convert(src)
        self.assertIn(
            '<div class="text"><strong><em>超重要</em></strong> な指摘</div>',
            out,
        )

    def test_balloon_bolditalic_takes_priority_over_bold_and_italic(self) -> None:
        # ***foo*** は bold/italic 単独正規表現より先にマッチし、
        # `<strong><em>...</strong></em>` のような閉じタグ順序の壊れた出力にならない。
        src = _balloon("kuro-chan", "***A***")
        out = convert_article_html.convert(src)
        self.assertNotIn("<strong><em>A</strong></em>", out)
        self.assertIn("<strong><em>A</em></strong>", out)


class BlueskyConvertTest(unittest.TestCase):
    def _basic_block(self, *, text: str = "投稿本文") -> str:
        return _bluesky({
            "did": "did:plc:abcdef",
            "cid": "bafyabcdef",
            "rkey": "3lmnopqr",
            "handle": "example.bsky.social",
            "display-name": "表示名",
            "created-at": "2026-05-14T01:33:34.400Z",
            "lang": "ja",
            "text": text,
        })

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
        block = _bluesky({
            "did": "did:plc:abc",
            "cid": "bafyabc",
            "rkey": "3xyz",
            "handle": "h.bsky.social",
            "display-name": "name",
            "created-at": "2026-05-14T00:00:00Z",
            "text": "hi",
        })
        out = convert_article_html.convert(block)
        self.assertIn('<p lang="ja">hi</p>', out)

    def test_bluesky_text_is_html_escaped(self) -> None:
        out = convert_article_html.convert(self._basic_block(text="<script>alert(1)</script>"))
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)

    def test_bluesky_text_multiline(self) -> None:
        # text= の値は閉じフェンスまで連結される（改行をそのまま保持）。
        block = (
            f"{BLUESKY_OPEN_TOKEN}\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=1 行目\n"
            "2 行目\n"
            "3 行目\n"
            f"{BLUESKY_CLOSE_TOKEN}\n"
        )
        out = convert_article_html.convert(block)
        # 改行を含む値が HTML エスケープされてそのまま入る
        self.assertIn("1 行目\n2 行目\n3 行目", out)

    def test_bluesky_full_width_colon_in_did_is_normalized(self) -> None:
        block = _bluesky({
            "did": "did：plc：abc",
            "cid": "bafyabc",
            "rkey": "3xyz",
            "handle": "h.bsky.social",
            "display-name": "name",
            "created-at": "2026-05-14T00:00:00Z",
            "text": "hi",
        })
        out = convert_article_html.convert(block)
        self.assertIn("did:plc:abc", out)
        self.assertNotIn("did：plc：abc", out)

    def test_bluesky_missing_required_key_raises(self) -> None:
        block = _bluesky({
            "did": "did:plc:abc",
            # cid 欠落
            "rkey": "3xyz",
            "handle": "h.bsky.social",
            "display-name": "name",
            "created-at": "2026-05-14T00:00:00Z",
            "text": "hi",
        })
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_unknown_key_raises(self) -> None:
        block = _bluesky({
            "did": "did:plc:abc",
            "cid": "bafyabc",
            "rkey": "3xyz",
            "handle": "h.bsky.social",
            "display-name": "name",
            "created-at": "2026-05-14T00:00:00Z",
            "extra": "おかしなキー",
            "text": "hi",
        })
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_unclosed_raises(self) -> None:
        # 閉じ }}} なし
        block = (
            f"{BLUESKY_OPEN_TOKEN}\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
        )
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_nested_balloon_raises(self) -> None:
        # bluesky ブロック内に balloon マーカーが現れた場合は入れ子エラー。
        block = (
            f"{BLUESKY_OPEN_TOKEN}\n"
            "did=did:plc:abc\n"
            f"{_balloon('kuro-chan', 'うっかり入れ子')}"
            f"{BLUESKY_CLOSE_TOKEN}\n"
        )
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_blank_line_inside_block_raises(self) -> None:
        # bluesky ブロック内 (text= 行より前) に空行を入れるとエラー停止。
        # 書き手が開きマーカーを `{{bluesky`（{ 2 個）と書いて閉じだけ正しく書く事故を防ぐ。
        block = (
            f"{BLUESKY_OPEN_TOKEN}\n"
            "did=did:plc:abc\n"
            "\n"  # 空行混入
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=hi\n"
            f"{BLUESKY_CLOSE_TOKEN}\n"
        )
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(block)

    def test_bluesky_text_containing_balloon_marker_is_not_treated_as_nested(self) -> None:
        # text= 行以降の値部分は入れ子検知の対象外。Bluesky 投稿本文に
        # balloon マーカー文字列や {{{bluesky が含まれていても text 値として通過する。
        block = (
            f"{BLUESKY_OPEN_TOKEN}\n"
            "did=did:plc:abc\n"
            "cid=bafyabc\n"
            "rkey=3xyz\n"
            "handle=h.bsky.social\n"
            "display-name=name\n"
            "created-at=2026-05-14T00:00:00Z\n"
            "text=以下は引用です\n"
            "kuro-chan>>これは Bluesky の投稿本文の一部であって balloon ではない\n"
            "{{{bluesky の説明をしている文章\n"
            f"{BLUESKY_CLOSE_TOKEN}\n"
        )
        # 入れ子検知が発火しないこと（例外を投げず正常に変換できること）
        out = convert_article_html.convert(block)
        self.assertIn('class="bluesky-embed"', out)
        # 本文文字列が HTML エスケープされて含まれること
        self.assertIn("kuro-chan&gt;&gt;", out)
        self.assertIn("{{{bluesky", out)

    def test_isolated_close_token_raises(self) -> None:
        # 対応する {{{bluesky のない孤立した }}} が地の文に出現したらエラー停止。
        # 書き手が開きマーカーを `{{bluesky`（{ 2 個）と誤記したケースを検出するため。
        src = f"通常段落\n\n{BLUESKY_CLOSE_TOKEN}\n\n別の段落\n"
        with self.assertRaises(convert_article_html.ConvertError):
            convert_article_html.convert(src)


class MixedConvertTest(unittest.TestCase):
    def test_balloon_and_bluesky_coexist(self) -> None:
        src = (
            _balloon("kuro-chan", "セリフ")
            + "\n"
            + _bluesky({
                "did": "did:plc:a",
                "cid": "bafya",
                "rkey": "3a",
                "handle": "h.bsky.social",
                "display-name": "n",
                "created-at": "2026-05-14T00:00:00Z",
                "text": "t",
            })
            + "\n"
            + _balloon("nee-san", "おっけー")
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
