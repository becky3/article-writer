"""replace_pr_placeholders.py の単体テスト.

仕様: aidlc-archive/68/plan-work/issue-68.md (PR #70 レビュー指摘 5 対応)

実行:

    python -m unittest tests.test_replace_pr_placeholders
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "replace_pr_placeholders.py"


def run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ReplaceTest(unittest.TestCase):
    def _write_temp(self, content: str) -> pathlib.Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        )
        tmp.write(content)
        tmp.close()
        return pathlib.Path(tmp.name)

    def test_basic_replacement(self) -> None:
        target = self._write_temp("title: {{TITLE}}\ndate: {{DATE}}\n")
        try:
            result = run_script([str(target), "TITLE", "Hello World", "DATE", "2026-05-20"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "title: Hello World\ndate: 2026-05-20\n")
        finally:
            target.unlink()

    def test_ampersand_value(self) -> None:
        target = self._write_temp("link: {{URL}}\n")
        try:
            result = run_script([str(target), "URL", "https://example.com/?a=1&b=2"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "link: https://example.com/?a=1&b=2\n")
        finally:
            target.unlink()

    def test_backslash_value(self) -> None:
        target = self._write_temp("path: {{PATH}}\n")
        try:
            result = run_script([str(target), "PATH", "C:\\Users\\test"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "path: C:\\Users\\test\n")
        finally:
            target.unlink()

    def test_pipe_value(self) -> None:
        target = self._write_temp("note: {{NOTE}}\n")
        try:
            result = run_script([str(target), "NOTE", "A|B|C"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "note: A|B|C\n")
        finally:
            target.unlink()

    def test_japanese_value(self) -> None:
        target = self._write_temp("title: {{TITLE}}\n")
        try:
            result = run_script([str(target), "TITLE", "日本語タイトル & 記号"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "title: 日本語タイトル & 記号\n")
        finally:
            target.unlink()

    def test_multiple_occurrences(self) -> None:
        target = self._write_temp("a: {{KEY}}\nb: {{KEY}}\n")
        try:
            result = run_script([str(target), "KEY", "value"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "a: value\nb: value\n")
        finally:
            target.unlink()

    def test_missing_placeholder_fails(self) -> None:
        target = self._write_temp("title: {{TITLE}}\n")
        try:
            result = run_script([str(target), "TITLE", "T", "MISSING", "M"])
            self.assertEqual(result.returncode, 2)
            self.assertIn("MISSING", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "title: {{TITLE}}\n")
        finally:
            target.unlink()

    def test_nonexistent_file_fails(self) -> None:
        result = run_script(["/nonexistent/path/foo.md", "KEY", "value"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("failed to read", result.stderr)

    def test_insufficient_args_fails(self) -> None:
        result = run_script(["file.md"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage:", result.stderr)

    def test_odd_args_fails(self) -> None:
        target = self._write_temp("x: {{X}}\n")
        try:
            result = run_script([str(target), "X", "v", "Y"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("Usage:", result.stderr)
        finally:
            target.unlink()


if __name__ == "__main__":
    unittest.main()
