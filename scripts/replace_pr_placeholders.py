"""PR テンプレ内のプレースホルダ `{{KEY}}` をリテラル置換する。

`/auto-publish-diary` スキルの Phase 3 で呼び出される補助スクリプト。
`str.replace` を用いるため、置換値に `&` / `\\` / `|` 等の sed/awk 特殊文字を
含んでいてもエスケープ不要。

Usage:
    python scripts/replace_pr_placeholders.py <file> KEY1 VALUE1 [KEY2 VALUE2 ...]

ファイルは UTF-8 で読み書きし、in-place で更新する。

指定した全キーが対象ファイル内に 1 回以上存在することを検証し、未置換キーが
あれば終了コード 2 で異常終了する（テンプレ更新でプレースホルダ名がずれた
場合の検出のため）。I/O 例外時は終了コード 1 でエラーメッセージを stderr に出力する。
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
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"ERROR: failed to read {target}: {exc}\n")
        return 1

    pairs = list(zip(sys.argv[2::2], sys.argv[3::2]))
    missing_keys = []
    for key, value in pairs:
        placeholder = "{{" + key + "}}"
        if placeholder not in text:
            missing_keys.append(key)
            continue
        text = text.replace(placeholder, value)

    if missing_keys:
        sys.stderr.write(
            f"ERROR: placeholders not found in {target}: "
            + ", ".join("{{" + k + "}}" for k in missing_keys)
            + "\n"
        )
        return 2

    try:
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"ERROR: failed to write {target}: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
