"""進行パターンを 1 つ選定する（フォールバックの機械的選定）.

仕様: .claude/skills/write-hatena-diary/SKILL.md（Phase 7 進行パターン選定）

役割:

- 素材合致による優先選択（content-match）は LLM 判断のため本スクリプトの対象外。
  本スクリプトは「強い合致がないとき」のフォールバック選定を担い、実行者による
  手順のブレをなくす（毎回同じ手続きで選ぶ）。
- 進行パターン ID の SSoT は ``narrative-guidelines.md``「進行パターン」。本スクリプトは
  そこから ID 一覧を抽出するだけで、ID を二重定義しない。

処理:

1. ``narrative-guidelines.md``「進行パターン」セクションから ID 一覧を抽出
2. ``articles/hatena/`` の日記記事フロントマター ``pattern`` を新しい順に最大 5 件読む
   （ファイル名の日付降順。``archive/`` は対象外）
3. 直近 5 件を除いた集合から乱数で 1 つ選び、ID を標準出力に印字する
   （除外で空になる場合は全 ID から選ぶ）

使用例:

    python scripts/select_pattern.py
"""
from __future__ import annotations

import pathlib
import random
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
NARRATIVE_GUIDE = (
    REPO_ROOT / ".claude" / "skills" / "write-hatena-diary" / "narrative-guidelines.md"
)
ARTICLES_DIR = REPO_ROOT / "articles" / "hatena"

# 直近この件数の pattern を重複回避のため除外する
RECENT_WINDOW = 5

_ARTICLE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-diary\.md$")
_PATTERN_HEADING_RE = re.compile(r"^## +進行パターン")
_SECTION_HEADING_RE = re.compile(r"^## ")
_PATTERN_DEF_RE = re.compile(r"^- \*\*([A-Z]):")
_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_FRONTMATTER_PATTERN_RE = re.compile(r"^pattern:\s*[\"']?([A-Za-z])[\"']?", re.MULTILINE)


def extract_pattern_ids(narrative_text: str) -> list[str]:
    """``narrative-guidelines.md``「進行パターン」セクションの ID 一覧を順序つきで返す."""
    ids: list[str] = []
    in_section = False
    for line in narrative_text.splitlines():
        if _PATTERN_HEADING_RE.match(line):
            in_section = True
            continue
        if in_section and _SECTION_HEADING_RE.match(line):
            break
        if in_section:
            m = _PATTERN_DEF_RE.match(line)
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


def _read_pattern(path: pathlib.Path) -> str | None:
    """記事ファイルのフロントマターから ``pattern`` の値（1 文字）を返す（無ければ None）."""
    text = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(text)
    frontmatter = fm_match.group(1) if fm_match else ""
    pat_match = _FRONTMATTER_PATTERN_RE.search(frontmatter)
    return pat_match.group(1) if pat_match else None


def read_recent_patterns(
    articles_dir: pathlib.Path, window: int = RECENT_WINDOW
) -> list[str]:
    """日記記事フロントマターの ``pattern`` を新しい順に最大 window 件返す（``archive/`` 除外）."""
    files = sorted(
        (p for p in articles_dir.glob("*.md") if _ARTICLE_NAME_RE.match(p.name)),
        reverse=True,
    )
    patterns: list[str] = []
    for path in files:
        pat = _read_pattern(path)
        if pat is not None:
            patterns.append(pat)
        if len(patterns) >= window:
            break
    return patterns


def select(ids: list[str], recent: list[str], rng: random.Random | None = None) -> str:
    """直近使用を除いた集合から 1 つ選ぶ（除外で空なら全 ID から選ぶ）."""
    if not ids:
        raise ValueError("進行パターン ID を抽出できませんでした")
    eligible = [i for i in ids if i not in recent] or ids
    chooser = rng if rng is not None else random
    return chooser.choice(eligible)


def main() -> int:
    ids = extract_pattern_ids(NARRATIVE_GUIDE.read_text(encoding="utf-8"))
    recent = read_recent_patterns(ARTICLES_DIR)
    print(select(ids, recent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
