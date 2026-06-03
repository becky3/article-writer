"""`/auto-publish-diary` の結果 JSON を `$PARENT_REPO/.tmp/auto-publish-diary/result.json` に書き出す。

呼び出し元（ai-assistant 等）が `claude -p` の出力経路差に依存せずファイル経由で
成否・URL 等を取得できるよう、出力契約をレスポンスファイル方式に統一する。

本スクリプトの出力契約定義および Phase ごとの呼び出し位置・引数組み合わせは
`.claude/skills/auto-publish-diary/SKILL.md`「出力仕様」セクションを参照する。

Usage（成功時、worktree 削除済み）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status ok \\
        --article-path articles/hatena/YYYY-MM-DD-diary.md \\
        --edit-url https://blog.hatena.ne.jp/<ID>/<BLOG>/edit?entry=<id> \\
        --public-url https://<blog>/entry/YYYY/MM/DD/000000 \\
        --pr-url https://github.com/.../pull/N \\
        --worktree-removed true

Usage（成功時、worktree 削除失敗）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status ok \\
        --article-path ... --edit-url ... --public-url ... --pr-url ... \\
        --worktree-removed false --worktree-path /abs/path/to/wt

Usage（失敗時）:
    python scripts/write_auto_publish_result.py \\
        --parent-repo /path/to/parent --status error \\
        --failed-phase environment \\
        --error "親リポに未コミット変更があります" \\
        [--worktree-path ... --article-path ... --edit-url ... --public-url ... --pr-url ...]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile


def build_result(
    *,
    status: str,
    article_path: str | None = None,
    edit_url: str | None = None,
    public_url: str | None = None,
    pr_url: str | None = None,
    worktree_removed: bool = False,
    worktree_path: str | None = None,
    failed_phase: str | None = None,
    error: str | None = None,
) -> dict:
    """result.json の中身（dict）を組み立てる.

    `auto_publish_diary.py`（orchestrator）と CLI の双方から呼ばれる共通ロジック。
    `status="ok"` のとき `worktree_removed=True` なら `worktree_path` は None に正規化する。
    """
    if status == "ok":
        return {
            "status": "ok",
            "article_path": article_path,
            "edit_url": edit_url,
            "public_url": public_url,
            "pr_url": pr_url,
            "merged": True,
            "worktree_removed": worktree_removed,
            "worktree_path": None if worktree_removed else worktree_path,
        }
    return {
        "status": "error",
        "failed_phase": failed_phase,
        "error": error,
        "article_path": article_path,
        "edit_url": edit_url,
        "public_url": public_url,
        "pr_url": pr_url,
        "merged": False,
        "worktree_removed": False,
        "worktree_path": worktree_path,
    }


def write_result_file(parent_repo: str, result: dict) -> None:
    """result.json を `<parent_repo>/.tmp/auto-publish-diary/result.json` に atomic 書き込みする.

    同一ディレクトリのテンポラリファイルへ書き出してから atomic rename で置き換える。
    書き込み途中のプロセス中断・ディスクフル等でも、既存 result.json の完全性を保つ
    （publish_hatena.py の published.jsonl 更新と同じパターン）。

    Raises:
        OSError: ディレクトリ作成・テンポラリ作成・書き込み・置換のいずれか失敗時
    """
    target_dir = pathlib.Path(parent_repo) / ".tmp" / "auto-publish-diary"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "result.json"
    payload = json.dumps(result, ensure_ascii=False) + "\n"
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".result.json.", dir=target_dir)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, target)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def validate(args: argparse.Namespace) -> str | None:
    if args.status == "ok":
        missing = [
            name
            for name in ("article_path", "edit_url", "public_url", "pr_url")
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
    parser.add_argument("--edit-url", default=None)
    parser.add_argument("--public-url", default=None)
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

    result = build_result(
        status=args.status,
        article_path=args.article_path,
        edit_url=args.edit_url,
        public_url=args.public_url,
        pr_url=args.pr_url,
        worktree_removed=args.worktree_removed == "true",
        worktree_path=args.worktree_path,
        failed_phase=args.failed_phase,
        error=args.error,
    )

    try:
        write_result_file(args.parent_repo, result)
    except OSError as exc:
        sys.stderr.write(f"ERROR: failed to write result.json under {args.parent_repo}: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
