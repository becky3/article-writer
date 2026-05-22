"""tests/test_convert_created_at_batch.py — convert_created_at_batch のテスト.

計画ファイル: aidlc-docs/plan-work/issue-133.md
テスト方針: ファイル読み書き + 行マッチ + 二重変換スキップ + 複数ブロック処理。
変換コアロジック（convert_utc_to_jst.convert）の再テストは行わない。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import convert_created_at_batch as batch  # noqa: E402


class ConvertFileTest(unittest.TestCase):
    def _write(self, path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")

    def test_single_z_line_is_converted(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            self._write(path, "created-at=2026-03-18T22:04:25.663Z\n")
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 1)
            self.assertEqual(skipped, 0)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "created-at=2026-03-19T07:04:25.663+09:00\n",
            )

    def test_already_jst_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            original = "created-at=2026-03-19T07:04:25.663+09:00\n"
            self._write(path, original)
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 0)
            self.assertEqual(skipped, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_multiple_blocks_in_one_file(self) -> None:
        body = (
            "text=hello\n"
            "created-at=2026-03-18T22:04:25.663Z\n"
            "text=world\n"
            "created-at=2026-03-19T07:10:13.667Z\n"
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            self._write(path, body)
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 2)
            self.assertEqual(skipped, 0)
            result = path.read_text(encoding="utf-8")
            self.assertIn("created-at=2026-03-19T07:04:25.663+09:00", result)
            self.assertIn("created-at=2026-03-19T16:10:13.667+09:00", result)
            self.assertIn("text=hello", result)
            self.assertIn("text=world", result)

    def test_mixed_z_and_jst(self) -> None:
        body = (
            "created-at=2026-03-18T22:04:25.663Z\n"
            "created-at=2026-03-19T07:04:25.663+09:00\n"
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            self._write(path, body)
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 1)
            self.assertEqual(skipped, 1)

    def test_non_target_lines_preserved(self) -> None:
        body = (
            "# Title\n"
            "\n"
            "Some narrative.\n"
            "created-at=2026-03-18T22:04:25.663Z\n"
            "\n"
            "More text including the word created-at= but not at line start.\n"
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            self._write(path, body)
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 1)
            result = path.read_text(encoding="utf-8")
            self.assertIn("# Title", result)
            self.assertIn("Some narrative.", result)
            self.assertIn(
                "More text including the word created-at= but not at line start.",
                result,
            )

    def test_no_target_lines_does_not_modify(self) -> None:
        body = "no created-at here\n"
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            self._write(path, body)
            before_mtime = path.stat().st_mtime_ns
            converted, skipped = batch.convert_file(path)
            self.assertEqual(converted, 0)
            self.assertEqual(skipped, 0)
            self.assertEqual(path.stat().st_mtime_ns, before_mtime)


class IterTargetFilesTest(unittest.TestCase):
    def test_single_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            path.write_text("x", encoding="utf-8")
            self.assertEqual(batch.iter_target_files(path), [path])

    def test_directory_recursive(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.md").write_text("", encoding="utf-8")
            (root / "sub" / "ignore.txt").write_text("", encoding="utf-8")
            files = batch.iter_target_files(root)
            self.assertEqual([p.name for p in files], ["a.md", "b.md"])


class MainCliTest(unittest.TestCase):
    def test_nonexistent_path_returns_1(self) -> None:
        rc = batch.main(["/nonexistent/path/zzz"])
        self.assertEqual(rc, 1)

    def test_successful_run_returns_0(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "created-at=2026-03-18T22:04:25.663Z\n", encoding="utf-8"
            )
            rc = batch.main([str(root)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
