"""記事 Markdown 内の簡素記法ブロックを HTML に変換する.

仕様: .claude/skills/write-hatena-diary/balloon-html.md

対象記法:

- ``:::kuro-chan`` / ``:::nee-san`` … 吹き出し（balloon-l / balloon-r）
- ``:::bluesky`` … Bluesky 投稿の埋め込みカード

使用例:

    python scripts/convert_article_html.py articles/hatena/2026-05-14-...md
    # → 変換後の Markdown を stdout に出力

    python scripts/convert_article_html.py - < input.md > output.md
    # → stdin から読み stdout に書く

``/publish-hatena`` 投稿時は ``convert(body)`` 関数として import される。
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys

BALLOON_OPEN_RE = re.compile(r"^:::(kuro-chan|nee-san)\s*$")
BLUESKY_OPEN_RE = re.compile(r"^:::bluesky\s*$")
FENCE_CLOSE_RE = re.compile(r"^:::\s*$")
ANY_OPEN_RE = re.compile(r"^:::[A-Za-z]")

# キャラ名 → CSS 側 (l/r) のマッピング。CSS クラス名 balloon-l / balloon-r は変えず、
# 入力記法だけキャラ名直結にする方針（マーカーがキャラ取り違えを誘発しないため）。
BALLOON_NAME_TO_SIDE = {
    "kuro-chan": "l",
    "nee-san": "r",
}
# balloon 本文内の Markdown 風インラインコード（`...`）を <code>...</code> に
# 自動置換するための正規表現。
# balloon は HTML の <div> 内に展開され Markdown が効かないため、書き手の
# 入力を `agent-commons` のように Markdown 風に統一できるよう変換器側で吸収する。
# 書き手は balloon の内外を問わず `...` で書ける（balloon の外は Markdown が
# 効くため backtick がそのまま <code> 体になり、内側は本関数で置換される）。
BALLOON_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
# balloon 本文内の Markdown 風文字装飾を対応 HTML タグに自動置換するための正規表現。
# 内側の最初と最後が非空白であることを要求する（`\S(?:[^...\n]*?\S)?` パターン）。
# これにより、地の文の単独 `*` `**` `~~`（例: `2 * 3 = 6`・`2 ** 3` 等）が誤発火
# しない。CommonMark の強調記号の境界条件に近い挙動。
# 適用順序は bold → italic（bold を先に処理しないと `**foo**` が `*foo*` の
# italic として誤マッチする）。strike は文字種が完全に分かれている（`~`）ため
# 順序は他 2 つと独立で、bold と italic の間に置く。
BALLOON_BOLD_RE = re.compile(r"\*\*(\S(?:[^*\n]*?\S)?)\*\*")
BALLOON_STRIKE_RE = re.compile(r"~~(\S(?:[^~\n]*?\S)?)~~")
BALLOON_ITALIC_RE = re.compile(r"\*(\S(?:[^*\n]*?\S)?)\*")
# 装飾置換の前に <code>...</code> 内部をプレースホルダーへ退避するための正規表現。
# code 内の `**` `*` `~~` を装飾として誤発火させないため、置換 → 装飾変換 → 復元
# の 3 段で処理する。
BALLOON_CODE_TAG_RE = re.compile(r"<code>.*?</code>")
BALLOON_CODE_PLACEHOLDER = "\x00CODE{}\x00"

REQUIRED_BLUESKY_KEYS = (
    "did",
    "cid",
    "rkey",
    "handle",
    "display-name",
    "created-at",
    "text",
)


def _normalize_did(value: str) -> str:
    """全角コロン（U+FF1A）を半角コロン（U+003A）に正規化する."""
    return value.replace("：", ":")


def build_balloon(side: str, body_text: str) -> str:
    """balloon HTML を組み立てる.

    ``side`` は ``"l"`` または ``"r"``。``body_text`` は改行を半角スペースに圧縮した上で
    ``<div class="text">`` の中に入れる。本文は HTML 直書きとして扱うため、エスケープしない。

    balloon 内の Markdown 風インラインコード（``` `name` ``` 形式）は ``<code>name</code>``
    に自動置換する。これにより書き手は balloon の内外を問わず同じ書き方
    （``` `agent-commons` ```）でリポ名・コード断片を表現できる。書き手が直接
    ``<code>...</code>`` を書いた場合はそのまま通る（HTML 直書きの性質を保つ）。

    さらに Markdown 風の文字装飾を以下のように自動置換する:

    - ``**foo**`` → ``<strong>foo</strong>``
    - ``~~foo~~`` → ``<del>foo</del>``
    - ``*foo*`` → ``<em>foo</em>``

    各装飾は内側の最初と最後が **非空白** であることを要求する。これにより
    地の文の単独 ``*`` ``**`` ``~~``（例: ``2 * 3 = 6``）が誤発火しない。

    装飾は ``<code>...</code>`` の外側のみ作用する（code 内部はプレースホルダー
    退避により装飾置換から保護される）。アンダースコア形式（``__bold__`` /
    ``_italic_``）は日本語混じり文での誤爆リスクが高いため非対応。
    """
    compact = re.sub(r"\s*\n\s*", " ", body_text.strip())
    compact = BALLOON_INLINE_CODE_RE.sub(r"<code>\1</code>", compact)
    code_segments: list[str] = []

    def _store(match: re.Match[str]) -> str:
        code_segments.append(match.group(0))
        return BALLOON_CODE_PLACEHOLDER.format(len(code_segments) - 1)

    compact = BALLOON_CODE_TAG_RE.sub(_store, compact)
    compact = BALLOON_BOLD_RE.sub(r"<strong>\1</strong>", compact)
    compact = BALLOON_STRIKE_RE.sub(r"<del>\1</del>", compact)
    compact = BALLOON_ITALIC_RE.sub(r"<em>\1</em>", compact)
    for idx, segment in enumerate(code_segments):
        compact = compact.replace(BALLOON_CODE_PLACEHOLDER.format(idx), segment)
    return (
        f'<div class="balloon balloon-{side}">'
        f'<div class="icon"></div>'
        f'<div class="text">{compact}</div>'
        f"</div>"
    )


def build_bluesky(fields: dict[str, str]) -> str:
    """Bluesky 埋め込み HTML を組み立てる.

    全ての値は HTML エスケープして埋め込む。``lang`` は省略時 ``"ja"``。
    """
    did = html.escape(_normalize_did(fields["did"]), quote=True)
    cid = html.escape(fields["cid"], quote=True)
    rkey = html.escape(fields["rkey"], quote=True)
    handle = html.escape(fields["handle"], quote=True)
    display_name = html.escape(fields["display-name"])
    text = html.escape(fields["text"])
    created_at = html.escape(fields["created-at"])
    lang = html.escape(fields.get("lang", "ja"), quote=True)

    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    profile_url = f"https://bsky.app/profile/{did}?ref_src=embed"
    post_url_embed = f"https://bsky.app/profile/{did}/post/{rkey}?ref_src=embed"
    post_url_cite = f"https://bsky.app/profile/{handle}/post/{rkey}"

    return (
        f'<blockquote class="bluesky-embed" data-bluesky-uri="{uri}" '
        f'data-bluesky-cid="{cid}">\n'
        f'<p lang="{lang}">{text}</p>\n'
        f"— "
        f'<a href="{profile_url}">{display_name} (@{handle})</a> '
        f'<a href="{post_url_embed}">{created_at}</a></blockquote>\n'
        f"<p>\n"
        f'<script async="" src="https://embed.bsky.app/static/embed.js" '
        f'charset="utf-8"></script>\n'
        f'<cite class="hatena-citation">'
        f'<a href="{post_url_cite}">bsky.app</a></cite></p>'
    )


def _parse_bluesky_fields(lines: list[str], block_start_lineno: int) -> dict[str, str]:
    """``:::bluesky`` ブロック内の key=value 行群をパースして dict にする.

    ``text=`` は ``text=`` 行以降、ブロック終端までを連結して値とする（複数行 text 対応）。
    必須キーの欠落・未知キーは ``ConvertError`` で停止する。
    """
    fields: dict[str, str] = {}
    text_lines: list[str] | None = None
    for offset, line in enumerate(lines):
        if text_lines is not None:
            text_lines.append(line)
            continue
        if "=" not in line:
            raise ConvertError(
                f"行 {block_start_lineno + offset + 1}: bluesky ブロック内に "
                f"'key=value' でない行があります: {line!r}",
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in REQUIRED_BLUESKY_KEYS and key != "lang":
            raise ConvertError(
                f"行 {block_start_lineno + offset + 1}: bluesky ブロックで未知のキー: {key!r}",
            )
        if key == "text":
            text_lines = [value]
        else:
            fields[key] = value
    if text_lines is not None:
        fields["text"] = "\n".join(text_lines)
    missing = [k for k in REQUIRED_BLUESKY_KEYS if k not in fields]
    if missing:
        raise ConvertError(
            f"行 {block_start_lineno}: bluesky ブロックに必須キー欠落: {', '.join(missing)}",
        )
    return fields


class ConvertError(Exception):
    """変換中の構文エラー."""


def convert(text: str) -> str:
    """記事本文の簡素記法ブロックを HTML に展開して返す.

    ブロック外の行はそのままパススルーする。
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        balloon_match = BALLOON_OPEN_RE.match(line)
        bluesky_match = BLUESKY_OPEN_RE.match(line)
        if balloon_match:
            name = balloon_match.group(1)
            side = BALLOON_NAME_TO_SIDE[name]
            block_start = i + 1
            body_lines: list[str] = []
            j = i + 1
            while j < n and not FENCE_CLOSE_RE.match(lines[j]):
                if ANY_OPEN_RE.match(lines[j]):
                    raise ConvertError(
                        f"行 {j + 1}: balloon ブロック内に別の ::: ブロック開始: {lines[j]!r}"
                        f"（入れ子は未サポート）",
                    )
                body_lines.append(lines[j])
                j += 1
            if j >= n:
                raise ConvertError(
                    f"行 {block_start}: :::{name} ブロックが閉じられていません",
                )
            out.append(build_balloon(side, "\n".join(body_lines)))
            i = j + 1
            continue
        if bluesky_match:
            block_start = i + 1
            body_lines = []
            j = i + 1
            while j < n and not FENCE_CLOSE_RE.match(lines[j]):
                if ANY_OPEN_RE.match(lines[j]):
                    raise ConvertError(
                        f"行 {j + 1}: bluesky ブロック内に別の ::: ブロック開始: "
                        f"{lines[j]!r}（入れ子は未サポート）",
                    )
                body_lines.append(lines[j])
                j += 1
            if j >= n:
                raise ConvertError(
                    f"行 {block_start}: :::bluesky ブロックが閉じられていません",
                )
            fields = _parse_bluesky_fields(body_lines, block_start)
            out.append(build_bluesky(fields))
            i = j + 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _read_input(path_arg: str) -> str:
    if path_arg == "-":
        return sys.stdin.read()
    path = pathlib.Path(path_arg)
    if not path.exists():
        raise SystemExit(f"記事ファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="記事 Markdown の簡素記法ブロックを HTML に変換する",
    )
    parser.add_argument(
        "path",
        help="記事 Markdown のパス。'-' を指定すると stdin から読む",
    )
    args = parser.parse_args(argv)
    text = _read_input(args.path)
    try:
        converted = convert(text)
    except ConvertError as e:
        print(f"❌ 変換エラー: {e}", file=sys.stderr)
        return 1
    sys.stdout.write(converted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
