"""記事 Markdown の簡素記法トークン定義 (SSoT).

仕様: .claude/skills/write-hatena-diary/balloon-html.md

本モジュールは ``convert_article_html.py`` (本体) と
``tests/test_convert_article_html.py`` (テスト) から参照される。
トークンを変更する場合は本ファイルのみを更新すれば、
正規表現・エラーメッセージ・テスト入力の全てに反映される。
"""
from __future__ import annotations

# balloon の単行マーカー suffix（キャラ名と本文の境界トークン）
BALLOON_MARKER_SUFFIX = ">>"

# balloon キャラ名 → CSS 側 (l/r) のマッピング。
# 本辞書のキーが balloon マーカー名の SSoT。
# 新キャラを追加する場合は本辞書に追記すれば、正規表現・エラーメッセージへ自動反映される。
BALLOON_NAME_TO_SIDE = {
    "kuro-chan": "l",
    "nee-san": "r",
}

# bluesky フェンスのブロック種別識別子
BLUESKY_BLOCK_NAME = "bluesky"

# bluesky フェンスの開閉トークン（視覚的にペアが対応する非対称マーカー、閉じ忘れ防止）
BLUESKY_OPEN_TOKEN = "{{{" + BLUESKY_BLOCK_NAME
BLUESKY_CLOSE_TOKEN = "}}}"
