"""UTC ISO 8601 文字列を JST ISO 8601 文字列に変換する CLI.

仕様: .claude/skills/write-hatena-diary/balloon-html.md

使用例:

    python scripts/convert_utc_to_jst.py 2026-03-18T22:04:25.663Z
    # → 2026-03-19T07:04:25.663+09:00

入力は末尾 ``Z`` または ``+00:00`` の UTC ISO 8601 文字列のみ受け付ける。
ミリ秒・マイクロ秒の桁数は入力の精度を維持する（秒精度入力は秒精度出力）。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
FRACTIONAL_RE = re.compile(r"\.(\d+)")


def convert(utc_str: str) -> str:
    """UTC ISO 8601 文字列を JST ISO 8601 文字列（``+09:00`` オフセット付き）に変換する."""
    s = utc_str.strip()
    if not s:
        raise ValueError("入力が空です")

    s_normalized = s[:-1] + "+00:00" if s.endswith("Z") else s

    try:
        dt = datetime.fromisoformat(s_normalized)
    except ValueError as exc:
        raise ValueError(f"ISO 8601 として解釈できません: {utc_str}") from exc

    if dt.tzinfo is None:
        raise ValueError(f"タイムゾーン情報がありません: {utc_str}")

    if dt.utcoffset() == timedelta(hours=9):
        raise ValueError(f"既に JST 形式です。重複変換していませんか?: {utc_str}")

    if dt.utcoffset() != timedelta(0):
        raise ValueError(f"UTC 以外のオフセットは受け付けません: {utc_str}")

    jst = dt.astimezone(JST)

    match = FRACTIONAL_RE.search(s)
    fractional_digits = len(match.group(1)) if match else 0

    body = jst.strftime("%Y-%m-%dT%H:%M:%S")
    if fractional_digits > 0:
        micro_str = f"{jst.microsecond:06d}"
        body += "." + micro_str[:fractional_digits]
    return body + "+09:00"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="UTC ISO 8601 文字列を JST ISO 8601 文字列に変換する"
    )
    parser.add_argument("utc", help="UTC ISO 8601 文字列（末尾 Z または +00:00）")
    args = parser.parse_args(argv)

    try:
        result = convert(args.utc)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
