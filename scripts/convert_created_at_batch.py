"""記事中の Bluesky `created-at` 行を UTC `Z` 形式から JST `+09:00` 形式へ一括変換する CLI.

仕様: aidlc-docs/plan-work/issue-133.md

使用例:

    python scripts/convert_created_at_batch.py articles/hatena/

ディレクトリ内の `*.md` を再帰的に走査し、各ファイル内の
`created-at=<UTC ISO 8601>Z` 行を `created-at=<JST ISO 8601>+09:00` 形式に書き換える。
既に `+09:00` 形式の行はスキップする（二重変換を防ぐ）。

変換ロジックは `convert_utc_to_jst.py` の `convert()` を再利用する。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from convert_utc_to_jst import convert

CREATED_AT_RE = re.compile(r"^(created-at=)(.+)$")


def convert_file(path: Path) -> tuple[int, int]:
    """1 ファイルを変換する.

    Returns:
        (converted_count, skipped_count): 変換した行数とスキップした行数
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    converted = 0
    skipped = 0
    new_lines: list[str] = []
    for line in lines:
        match = CREATED_AT_RE.match(line.rstrip("\r\n"))
        if match is None:
            new_lines.append(line)
            continue

        value = match.group(2).strip()
        if value.endswith("+09:00"):
            skipped += 1
            new_lines.append(line)
            continue

        jst_value = convert(value)
        ending = line[len(line.rstrip("\r\n")) :]
        new_lines.append(f"{match.group(1)}{jst_value}{ending}")
        converted += 1

    if converted > 0:
        path.write_text("".join(new_lines), encoding="utf-8")
    return converted, skipped


def iter_target_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(target.rglob("*.md"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bluesky created-at の UTC → JST 一括変換"
    )
    parser.add_argument(
        "target",
        type=Path,
        help="変換対象のファイルまたはディレクトリ（再帰）",
    )
    args = parser.parse_args(argv)

    if not args.target.exists():
        print(f"エラー: パスが存在しません: {args.target}", file=sys.stderr)
        return 1

    total_converted = 0
    total_skipped = 0
    files_modified = 0
    for path in iter_target_files(args.target):
        try:
            converted, skipped = convert_file(path)
        except ValueError as exc:
            print(f"エラー: {path}: {exc}", file=sys.stderr)
            return 1
        if converted > 0:
            print(f"✏️  {path}: {converted} 件変換")
            files_modified += 1
        total_converted += converted
        total_skipped += skipped

    print(
        f"\n📊 完了: ファイル {files_modified} 件 / 変換 {total_converted} 行 "
        f"/ スキップ {total_skipped} 行（既に JST）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
