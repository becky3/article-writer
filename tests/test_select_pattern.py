"""select_pattern.py のユニットテスト.

仕様: .claude/skills/write-hatena-diary/SKILL.md（Phase 4-4 進行パターン選定）
計画: aidlc-docs/plan-work/issue-205.md（テスト方針）

実行:

    python -m unittest tests.test_select_pattern
"""
from __future__ import annotations

import pathlib
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import select_pattern  # noqa: E402


# 「進行パターン」セクション内の ID 定義に加え、セクション**外**（面白味の要素）に
# ID 形式 `- **Z: ...**` の decoy を置く。セクションスコープが効いていれば Z は拾わない。
SAMPLE_NARRATIVE = """# 物語ガイド

## 進行パターン（L2 構成エンジン・必須）

### パターン一覧

**平常** — A

- **A: 平常運転** — 通常の作業実況
- **B: 共闘・結託** — 二人がかり
- **C: 同時遭遇** — 並列で直面

**特殊** — X

- **X: カオス展開** — 構成を崩す

## 面白味の要素（参考）

- **Z: にせ見出し** — パターンセクション外なので拾ってはいけない
- **リアクション主導**: 笑いは受け手から
"""


class ExtractPatternIdsTest(unittest.TestCase):
    def test_extracts_ids_in_order_and_stops_at_next_section(self) -> None:
        self.assertEqual(
            select_pattern.extract_pattern_ids(SAMPLE_NARRATIVE),
            ["A", "B", "C", "X"],
        )

    def test_excludes_id_like_bold_after_section(self) -> None:
        # 次セクション（面白味の要素）にある ID 形式 `- **Z: ...**` は拾わない
        self.assertNotIn("Z", select_pattern.extract_pattern_ids(SAMPLE_NARRATIVE))

    def test_empty_when_no_pattern_section(self) -> None:
        self.assertEqual(select_pattern.extract_pattern_ids("# 見出しのみ\n本文\n"), [])


class SelectTest(unittest.TestCase):
    def test_excludes_recent(self) -> None:
        ids = ["A", "B", "C", "D"]
        recent = ["A", "B"]
        rng = random.Random(0)
        for _ in range(30):
            self.assertIn(select_pattern.select(ids, recent, rng), ["C", "D"])

    def test_falls_back_to_all_when_all_excluded(self) -> None:
        ids = ["A", "B"]
        recent = ["A", "B"]
        self.assertIn(
            select_pattern.select(ids, recent, random.Random(0)), ["A", "B"]
        )

    def test_raises_on_empty_ids(self) -> None:
        with self.assertRaises(ValueError):
            select_pattern.select([], [])


class ReadRecentPatternsTest(unittest.TestCase):
    @staticmethod
    def _write_article(
        base: pathlib.Path, date: str, pattern: str | None, *, quoted: bool = True
    ) -> None:
        if pattern is None:
            pat_line = ""
        elif quoted:
            pat_line = f'pattern: "{pattern}"\n'
        else:
            pat_line = f"pattern: {pattern}\n"
        (base / f"{date}-diary.md").write_text(
            f'---\ntitle: "t"\ndate: "{date}"\ncategory: "diary"\n{pat_line}---\n本文\n',
            encoding="utf-8",
        )

    def test_reads_recent_newest_first_and_ignores_non_diary_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            self._write_article(base, "2026-02-01", "A")
            self._write_article(base, "2026-02-02", "B")
            self._write_article(base, "2026-02-03", "C")
            (base / "published.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                select_pattern.read_recent_patterns(base, window=2), ["C", "B"]
            )

    def test_window_caps_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            for i in range(1, 8):
                self._write_article(base, f"2026-02-0{i}", "A")
            self.assertEqual(
                len(select_pattern.read_recent_patterns(base, window=5)), 5
            )

    def test_skips_article_without_pattern_and_reads_unquoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            self._write_article(base, "2026-02-01", "A")
            self._write_article(base, "2026-02-02", None)  # pattern 欠落 → スキップ
            self._write_article(base, "2026-02-03", "C", quoted=False)  # クォートなし
            self.assertEqual(
                select_pattern.read_recent_patterns(base, window=5), ["C", "A"]
            )


if __name__ == "__main__":
    unittest.main()
