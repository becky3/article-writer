"""`/auto-publish-diary` の結果 JSON を `$PARENT_REPO/.tmp/auto-publish-diary/result.json` に書き出す。

呼び出し元（ai-assistant 等）が `claude -p` の出力経路差に依存せずファイル経由で
成否・URL 等を取得できるよう、出力契約をレスポンスファイル方式に統一する。

出力契約（result.json スキーマ）の SSoT は本ファイルの `build_result()`。Phase ごとの呼び出し位置・引数組み合わせの運用文脈は
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
        --worktree-removed false --worktree-path /abs/path/to/wt \\
        --worktree-remove-error "fatal: '/abs/path/to/wt' is not a working tree"

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

# in-flight マーカー: setup 成功時に作成され、result.json 書き込みで削除される。
# 「マーカーあり + result.json 不在」= 生成〜finalize 間で実行が途切れた状態を表し、
# Stop hook（.claude/scripts/auto-publish-stop-guard.sh）が finalize 未実行の検出に使う
IN_FLIGHT_FILENAME = "in-flight"
# Stop hook のブロック回数カウンタ。setup でリセットし、result.json 書き込みで削除する
STOP_BLOCK_COUNT_FILENAME = "stop-block-count"
# 自動投稿セッションの自己識別ファイル。setup が自セッションの CLAUDE_CODE_SESSION_ID を
# 記録し、Stop hook は「記録された ID と自分のセッション ID が一致するときだけ」ブロックする
# （並行する開発セッションを誤ブロックしないため）。result.json 書き込みで削除する
SESSION_ID_FILENAME = "session-id"


def result_dir(parent_repo: str) -> pathlib.Path:
    """result.json・in-flight マーカー等を配置する状態ディレクトリを返す."""
    return pathlib.Path(parent_repo) / ".tmp" / "auto-publish-diary"


def build_result(
    *,
    status: str,
    article_path: str | None = None,
    edit_url: str | None = None,
    public_url: str | None = None,
    pr_url: str | None = None,
    worktree_removed: bool = False,
    worktree_path: str | None = None,
    worktree_remove_error: str | None = None,
    failed_phase: str | None = None,
    error: str | None = None,
) -> dict:
    """result.json の中身（dict）を組み立てる（出力スキーマの SSoT）.

    `auto_publish_diary.py`（orchestrator）と CLI の双方から呼ばれる共通ロジック。
    `status="ok"` のとき `worktree_removed=True` なら `worktree_path` は None に正規化する。

    キー定義（status="ok" / "error" で共通スキーマ。値の意味は status で変わる）:

    - status: "ok"（全 Phase 成功。`worktree_removed=false` の中間状態を含む）/ "error"（任意 Phase で停止）
    - article_path: 生成記事の相対パス。生成前に失敗した場合は None
    - edit_url: はてなブログの編集ページ URL（`https://blog.hatena.ne.jp/<ID>/<BLOG>/edit?entry=<id>`）。
      下書き状態でも所有者がアクセスできる。投稿前に失敗した場合は None
    - public_url: 公開記事 URL（`https://<BLOG>/entry/YYYY/MM/DD/000000`、記事日付ベースで算出。
      公開されるまでは 404）。投稿前に失敗した場合は None
    - pr_url: 作成された PR の URL。PR 作成前に失敗した場合は None
    - merged: PR がリモートでマージ済みなら true（status="ok" なら必ず true、"error" なら必ず false）
    - worktree_removed: cleanup で worktree が削除済みなら true。削除失敗時 / 失敗終了時は false
    - worktree_path: 削除失敗時は残置 worktree の絶対パス。削除済みなら None。
      worktree 作成前に失敗した場合は None
    - worktree_remove_error: `git worktree remove --force` の stderr 1 行要約。
      - status="error" 時 / `git worktree remove` 自体が呼ばれなかった場合は None
      - `git worktree remove` が失敗したとき（`os.rmdir` フォールバックの成否に関わらず）は元 stderr を保持する
      - `worktree_removed=true` + `worktree_remove_error` 非 null は「rmdir フォールバックが効いて削除成功」を意味する（#245）
    - failed_phase: status="error" のみ。失敗 Phase 名（`environment` / `write` / `publish` / `git`）。
      `cleanup` は仕様上 status="ok" で終了するため現れない。status="ok" 時はキー自体が省略される
    - error: status="error" のみのエラー要約 1 行。status="ok" 時はキー自体が省略される
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
            "worktree_remove_error": worktree_remove_error,
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
        "worktree_remove_error": None,
    }


def write_result_file(parent_repo: str, result: dict) -> None:
    """result.json を `<parent_repo>/.tmp/auto-publish-diary/result.json` に atomic 書き込みする.

    同一ディレクトリのテンポラリファイルへ書き出してから atomic rename で置き換える。
    書き込み途中のプロセス中断・ディスクフル等でも、既存 result.json の完全性を保つ
    （publish_hatena.py の published.jsonl 更新と同じパターン）。

    書き込み成功後、in-flight マーカー・Stop hook カウンタ・session-id を削除する
    （result.json が書かれた = 実行が終端に到達したため、Stop hook のブロック対象から外す）。
    マーカー削除の失敗は結果伝達に影響しないため握りつぶす。

    Raises:
        OSError: ディレクトリ作成・テンポラリ作成・書き込み・置換のいずれか失敗時
    """
    target_dir = result_dir(parent_repo)
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
    for name in (IN_FLIGHT_FILENAME, STOP_BLOCK_COUNT_FILENAME, SESSION_ID_FILENAME):
        try:
            (target_dir / name).unlink(missing_ok=True)
        except OSError:
            pass


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
    parser.add_argument("--worktree-remove-error", default=None)
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
        worktree_remove_error=args.worktree_remove_error,
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
