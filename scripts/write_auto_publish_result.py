"""`/auto-publish-diary` の結果 JSON を `$PARENT_REPO/.tmp/auto-publish-diary/result.json` に書き出す。

呼び出し元（ai-assistant 等）が `claude -p` の出力経路差に依存せずファイル経由で
成否・URL 等を取得できるよう、出力契約をレスポンスファイル方式に統一する。

本スクリプトの出力契約定義および Phase ごとの呼び出し位置・引数組み合わせは
`.claude/skills/auto-publish-diary/SKILL.md`「出力仕様」セクションを参照する。

Usage（成功時、worktree 削除済み）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status ok \\
        --article-path articles/hatena/YYYY-MM-DD-diary.md \\
        --draft-url https://blog/entry/... \\
        --pr-url https://github.com/.../pull/N \\
        --worktree-removed true

Usage（成功時、worktree 削除失敗）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status ok \\
        --article-path ... --draft-url ... --pr-url ... \\
        --worktree-removed false --worktree-path /abs/path/to/wt

Usage（失敗時）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status error \\
        --failed-phase environment \\
        --error "親リポに未コミット変更があります" \\
        [--worktree-path ... --article-path ... --draft-url ... --pr-url ...]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def build_result(args: argparse.Namespace) -> dict:
    if args.status == "ok":
        worktree_removed = args.worktree_removed == "true"
        worktree_path = None if worktree_removed else args.worktree_path
        return {
            "status": "ok",
            "article_path": args.article_path,
            "draft_url": args.draft_url,
            "pr_url": args.pr_url,
            "merged": True,
            "worktree_removed": worktree_removed,
            "worktree_path": worktree_path,
        }
    return {
        "status": "error",
        "failed_phase": args.failed_phase,
        "error": args.error,
        "article_path": args.article_path,
        "draft_url": args.draft_url,
        "pr_url": args.pr_url,
        "merged": False,
        "worktree_path": args.worktree_path,
    }


def validate(args: argparse.Namespace) -> str | None:
    if args.status == "ok":
        missing = [
            name
            for name in ("article_path", "draft_url", "pr_url")
            if getattr(args, name) is None
        ]
        if missing:
            return "--" + ", --".join(n.replace("_", "-") for n in missing) + " required when --status=ok"
        if args.worktree_removed is None:
            return "--worktree-removed required when --status=ok"
        if args.worktree_removed == "false" and args.worktree_path is None:
            return "--worktree-path required when --worktree-removed=false"
        return None

    missing = [name for name in ("failed_phase", "error") if getattr(args, name) is None]
    if missing:
        return "--" + ", --".join(n.replace("_", "-") for n in missing) + " required when --status=error"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--parent-repo", required=True, help="親リポジトリの絶対パス")
    parser.add_argument("--status", choices=["ok", "error"], required=True)
    parser.add_argument("--article-path", default=None)
    parser.add_argument("--draft-url", default=None)
    parser.add_argument("--pr-url", default=None)
    parser.add_argument("--worktree-removed", choices=["true", "false"], default=None)
    parser.add_argument("--worktree-path", default=None)
    parser.add_argument("--failed-phase", default=None)
    parser.add_argument("--error", default=None)
    args = parser.parse_args()

    err = validate(args)
    if err is not None:
        sys.stderr.write(f"ERROR: {err}\n")
        return 1

    target_dir = pathlib.Path(args.parent_repo) / ".tmp" / "auto-publish-diary"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"ERROR: failed to create {target_dir}: {exc}\n")
        return 1

    target = target_dir / "result.json"
    result = build_result(args)
    try:
        target.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"ERROR: failed to write {target}: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
