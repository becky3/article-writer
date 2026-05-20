"""PR テンプレ内のプレースホルダ `{{KEY}}` をリテラル置換する。

`/auto-publish-diary` スキルの Phase 3 で呼び出される補助スクリプト。
`str.replace` を用いるため、置換値に `&` / `\\` / `|` 等の sed/awk 特殊文字を
含んでいてもエスケープ不要。

Usage:
    python scripts/replace_pr_placeholders.py <file> KEY1 VALUE1 [KEY2 VALUE2 ...]

ファイルは UTF-8 で読み書きし、in-place で更新する。
"""

from __future__ import annotations

import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 4 or (len(sys.argv) - 2) % 2 != 0:
        sys.stderr.write(
            "Usage: python scripts/replace_pr_placeholders.py <file> KEY VALUE [KEY VALUE ...]\n"
        )
        return 1
    target = pathlib.Path(sys.argv[1])
    text = target.read_text(encoding="utf-8")
    pairs = list(zip(sys.argv[2::2], sys.argv[3::2]))
    for key, value in pairs:
        text = text.replace("{{" + key + "}}", value)
    target.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
