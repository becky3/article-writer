"""convert_utc_to_jst.py のユニットテスト.

仕様: .claude/skills/write-hatena-diary/balloon-html.md
計画: aidlc-docs/plan-work/issue-131.md (テスト方針)

実行:

    python -m unittest tests.test_convert_utc_to_jst
"""
from __future__ import annotations

import io
import pathlib
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import convert_utc_to_jst  # noqa: E402


class ConvertUtcToJstTest(unittest.TestCase):
    def test_z_suffix_with_milliseconds(self) -> None:
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.663Z"),
            "2026-03-19T07:04:25.663+09:00",
        )

    def test_z_suffix_seconds_precision(self) -> None:
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-19T07:10:13Z"),
            "2026-03-19T16:10:13+09:00",
        )

    def test_plus_zero_offset(self) -> None:
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.663+00:00"),
            "2026-03-19T07:04:25.663+09:00",
        )

    def test_day_boundary_crossing(self) -> None:
        # UTC 15:00 = JST 00:00 (翌日)
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T15:00:00Z"),
            "2026-03-19T00:00:00+09:00",
        )

    def test_year_boundary_crossing(self) -> None:
        # UTC 2025-12-31T15:00 = JST 2026-01-01T00:00
        self.assertEqual(
            convert_utc_to_jst.convert("2025-12-31T15:00:00Z"),
            "2026-01-01T00:00:00+09:00",
        )

    def test_microsecond_precision_preserved(self) -> None:
        # 6 桁マイクロ秒入力 → 6 桁マイクロ秒出力
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.663000Z"),
            "2026-03-19T07:04:25.663000+09:00",
        )

    def test_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            convert_utc_to_jst.convert("")

    def test_whitespace_only_input(self) -> None:
        with self.assertRaises(ValueError):
            convert_utc_to_jst.convert("   ")

    def test_invalid_iso8601(self) -> None:
        with self.assertRaises(ValueError):
            convert_utc_to_jst.convert("not-a-date")

    def test_no_timezone_offset(self) -> None:
        # naive datetime（タイムゾーン情報なし）はエラー
        with self.assertRaises(ValueError):
            convert_utc_to_jst.convert("2026-03-18T22:04:25.663")

    def test_already_jst_input_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            convert_utc_to_jst.convert("2026-03-19T07:04:25.663+09:00")
        self.assertIn("既に JST", str(ctx.exception))

    def test_one_digit_fractional(self) -> None:
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.6Z"),
            "2026-03-19T07:04:25.6+09:00",
        )

    def test_four_digit_fractional_preserved(self) -> None:
        # ISO 8601 仕様は任意桁を許容するため、stdlib 制約を内部で吸収して入力桁数を保持する
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.6630Z"),
            "2026-03-19T07:04:25.6630+09:00",
        )

    def test_five_digit_fractional_preserved(self) -> None:
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.66301Z"),
            "2026-03-19T07:04:25.66301+09:00",
        )

    def test_seven_digit_fractional_truncated_to_six(self) -> None:
        # stdlib の datetime はマイクロ秒（6 桁）までしか保持できないため、7 桁以上は 6 桁にトランケート
        self.assertEqual(
            convert_utc_to_jst.convert("2026-03-18T22:04:25.6630001Z"),
            "2026-03-19T07:04:25.663000+09:00",
        )

    def test_non_utc_offset_rejected(self) -> None:
        # +05:30 等の非 UTC オフセットはエラー
        with self.assertRaises(ValueError):
            convert_utc_to_jst.convert("2026-03-18T22:04:25.663+05:30")

    def test_cli_success(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = convert_utc_to_jst.main(["2026-03-18T22:04:25.663Z"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "2026-03-19T07:04:25.663+09:00")

    def test_cli_error_exits_nonzero(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = convert_utc_to_jst.main(["invalid-input"])
        self.assertEqual(exit_code, 1)
        self.assertIn("エラー", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
