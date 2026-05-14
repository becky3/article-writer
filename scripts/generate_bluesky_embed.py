"""Bluesky 投稿の HTML 埋め込みスニペット生成スクリプト.

はてなブログ Markdown モードの本文に貼り付けると、プレビュー時点で
Bluesky の投稿カードとして表示される HTML を生成する。

仕様: .claude/skills/write-hatena-diary/SKILL.md (Phase 4: Bluesky 引用)

使用例:

    python scripts/generate_bluesky_embed.py \\
        --did did:plc:lw4huzofvdhfvxibdrqeyzrl \\
        --cid bafyreiawns4f7zbsm2575d66zbgshp4vipb2d6s2bwe3upupmpyvvdywgu \\
        --rkey 3mlroeuo6k22w \\
        --handle rhythmcan.bsky.social \\
        --display-name becky \\
        --text "投稿本文" \\
        --created-at 2026-05-14T01:33:34.400Z

出力は stdout に複数行 HTML として返す。スキル側でこの出力を Markdown 本文に
そのまま挿入する想定。
"""
from __future__ import annotations

import argparse
import html
import sys


def normalize_did(value: str) -> str:
    """DID 文字列の全角コロン（U+FF1A）を半角コロン（U+003A）に正規化する.

    rag-knowledge 側の Bluesky source_id では DID が `did：plc：...` のように
    全角コロンで格納されている場合がある。Bluesky の at-uri / embed URL は
    半角コロンを期待するため、本関数で正規化する。

    DID 以外の引数（cid / handle / rkey / created_at 等）は本関数の対象外。
    これらは rag-knowledge 側で英数字・記号のみで格納される運用前提のため、
    全角コロンが混入する経路がない。将来別の引数で全角コロン混入が観測された
    場合は本関数の適用範囲を拡張するか、引数ごとに別の正規化関数を用意すること。
    """
    return value.replace("：", ":")


def build_snippet(
    *,
    did: str,
    cid: str,
    rkey: str,
    handle: str,
    display_name: str,
    text: str,
    created_at: str,
    lang: str = "ja",
) -> str:
    """Bluesky 埋め込みスニペットを生成する.

    全ての文字列入力は HTML エスケープして埋め込む。出力は Markdown 本文に
    そのまま貼り付け可能な HTML 文字列（改行を含む複数行）。
    """
    did_esc = html.escape(normalize_did(did), quote=True)
    cid_esc = html.escape(cid, quote=True)
    rkey_esc = html.escape(rkey, quote=True)
    handle_esc = html.escape(handle, quote=True)
    display_name_esc = html.escape(display_name)
    text_esc = html.escape(text)
    created_at_esc = html.escape(created_at)
    lang_esc = html.escape(lang, quote=True)

    uri = f"at://{did_esc}/app.bsky.feed.post/{rkey_esc}"
    profile_url = f"https://bsky.app/profile/{did_esc}?ref_src=embed"
    post_url_embed = (
        f"https://bsky.app/profile/{did_esc}/post/{rkey_esc}?ref_src=embed"
    )
    post_url_cite = f"https://bsky.app/profile/{handle_esc}/post/{rkey_esc}"

    return (
        f'<blockquote class="bluesky-embed" data-bluesky-uri="{uri}" '
        f'data-bluesky-cid="{cid_esc}">\n'
        f'<p lang="{lang_esc}">{text_esc}</p>\n'
        f"— "  # em dash
        f'<a href="{profile_url}">{display_name_esc} (@{handle_esc})</a> '
        f'<a href="{post_url_embed}">{created_at_esc}</a></blockquote>\n'
        f"<p>\n"
        f'<script async="" src="https://embed.bsky.app/static/embed.js" '
        f'charset="utf-8"></script>\n'
        f'<cite class="hatena-citation">'
        f'<a href="{post_url_cite}">bsky.app</a></cite></p>'
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bluesky 投稿の HTML 埋め込みスニペットを生成する",
    )
    parser.add_argument(
        "--did",
        required=True,
        help="投稿者の DID（例: did:plc:lw4huzofvdhfvxibdrqeyzrl）",
    )
    parser.add_argument(
        "--cid",
        required=True,
        help="投稿の CID（at-proto 投稿の content identifier）",
    )
    parser.add_argument(
        "--rkey",
        required=True,
        help="投稿の rkey（URL 末尾の識別子。例: 3mlroeuo6k22w）",
    )
    parser.add_argument(
        "--handle",
        required=True,
        help="投稿者のハンドル（例: rhythmcan.bsky.social）",
    )
    parser.add_argument(
        "--display-name",
        required=True,
        help="投稿者の表示名（例: becky）",
    )
    parser.add_argument(
        "--text",
        required=True,
        help=(
            "投稿本文（Bluesky 上の生テキスト）。"
            "改行を含む場合はシェルの引用ルールに従う"
            "（bash: $'...\\n...' / PowerShell: バッククォート + n）"
        ),
    )
    parser.add_argument(
        "--created-at",
        required=True,
        help="投稿日時（ISO 8601 / Bluesky API のフォーマット。例: 2026-05-14T01:33:34.400Z）",
    )
    parser.add_argument(
        "--lang",
        default="ja",
        help="投稿の言語コード（デフォルト: ja）",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snippet = build_snippet(
        did=args.did,
        cid=args.cid,
        rkey=args.rkey,
        handle=args.handle,
        display_name=args.display_name,
        text=args.text,
        created_at=args.created_at,
        lang=args.lang,
    )
    print(snippet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
