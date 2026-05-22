"""UTC ISO 8601 文字列を JST ISO 8601 文字列に変換する CLI.

仕様: .claude/skills/write-hatena-diary/balloon-html.md

使用例:

    python scripts/convert_utc_to_jst.py 2026-03-18T22:04:25.663Z
    # → 2026-03-19T07:04:25.663+09:00

入力は末尾 ``Z`` または ``+00:00`` の UTC ISO 8601 文字列のみ受け付ける。
小数秒は任意桁を受け付け、出力は入力桁数を保持する。
ただし stdlib の `datetime` がマイクロ秒（6 桁）までしか保持できないため、
7 桁以上の入力は 6 桁にトランケートして出力する。
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
    s_for_parsing, output_fractional_digits = _normalize_fractional(s_normalized)

    try:
        dt = datetime.fromisoformat(s_for_parsing)
    except ValueError as exc:
        raise ValueError(f"ISO 8601 として解釈できません: {utc_str}") from exc

    if dt.tzinfo is None:
        raise ValueError(f"タイムゾーン情報がありません: {utc_str}")

    if dt.utcoffset() == timedelta(hours=9):
        raise ValueError(f"既に JST 形式です。重複変換していませんか?: {utc_str}")

    if dt.utcoffset() != timedelta(0):
        raise ValueError(f"UTC 以外のオフセットは受け付けません: {utc_str}")

    jst = dt.astimezone(JST)

    body = jst.strftime("%Y-%m-%dT%H:%M:%S")
    if output_fractional_digits > 0:
        micro_str = f"{jst.microsecond:06d}"
        body += "." + micro_str[:output_fractional_digits]
    return body + "+09:00"


def _normalize_fractional(s: str) -> tuple[str, int]:
    """ISO 8601 文字列の小数秒桁数を stdlib (`datetime`) と互換になるよう正規化する.

    任意桁の入力を `datetime.fromisoformat` がパースできる形（Python 3.10 では 3 桁か 6 桁）に
    変換しつつ、出力時に使う桁数を返す。7 桁以上はマイクロ秒（6 桁）にトランケートする。

    Returns:
        (パース用に正規化した文字列, 出力に使う小数秒桁数)
    """
    match = FRACTIONAL_RE.search(s)
    if not match:
        return s, 0

    fractional = match.group(1)
    original_digits = len(fractional)

    if original_digits == 6:
        return s, 6
    if original_digits > 6:
        normalized = fractional[:6]
        output_digits = 6
    else:
        normalized = fractional.ljust(6, "0")
        output_digits = original_digits

    return s.replace(f".{fractional}", f".{normalized}", 1), output_digits


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
