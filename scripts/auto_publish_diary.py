"""`/auto-publish-diary` の決定論的オーケストレーション（Phase 0・2〜5）。

仕様: .claude/skills/auto-publish-diary/SKILL.md

記事生成（Phase 1）は `/write-hatena-diary` という Claude スキル（LLM）であり
スクリプト化できないため、本スクリプトは LLM ステップを挟んで 2 エントリに分かれる:

- `setup`: Phase 0（親リポ検証・clean 確認・main 最新化・worktree 作成・.env コピー）。
  worktree パスを stdout に `WORKTREE: <path>` 形式で出力する。
- `finalize --article-path <相対パス>`: Phase 2〜5（Hatena 投稿・git commit/push/PR/merge・
  worktree クリーンアップ・result.json 書き込み）。worktree 内を cwd として起動する。

共有核 `publish_hatena.py` への呼び出し方針（interface 混在方式）:

- 投稿という副作用は subprocess で起動する（共有核の構造を変えない）。
- URL は stdout を grep せず、投稿後 `published.jsonl` から `edit_url` を読み、
  純粋関数 `build_browser_edit_url` / `build_public_url` を import して組み立てる。

result.json 書き込みは `write_auto_publish_result` の関数を import し、単一の
`fail()` / `finish()` ヘルパーで一元化する（呼び出しごとの引数重複を避ける）。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

import publish_hatena
import write_auto_publish_result

# git ネットワーク操作のタイムアウト（秒）。SKILL.md の bash 実装と揃える
NETWORK_TIMEOUT = 120
# 非対話・接続タイムアウトを強制する SSH オプション（パスフレーズ待ち等のハングを防ぐ）
GIT_SSH_COMMAND = "ssh -o BatchMode=yes -o ConnectTimeout=30"


@dataclass
class PublishState:
    """Phase をまたいで蓄積する状態。fail() / finish() が result.json に反映する。"""

    parent_repo: str
    worktree_path: str | None = None
    branch_name: str | None = None
    article_path: str | None = None
    edit_url: str | None = None
    public_url: str | None = None
    pr_url: str | None = None


def _run(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int | None = None,
    network: bool = False,
) -> subprocess.CompletedProcess[str]:
    """subprocess 実行の共通ラッパ。network=True で SSH の非対話オプションを注入する。"""
    env = dict(os.environ)
    if network:
        env["GIT_SSH_COMMAND"] = GIT_SSH_COMMAND
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def fail(state: PublishState, *, failed_phase: str, error: str) -> None:
    """status=error の result.json を書き出して終了コード 1 で終了する（単一の失敗経路）。"""
    sys.stderr.write(f"[PHASE {failed_phase}] 失敗: {error}\n")
    result = write_auto_publish_result.build_result(
        status="error",
        failed_phase=failed_phase,
        error=error,
        article_path=state.article_path,
        edit_url=state.edit_url,
        public_url=state.public_url,
        pr_url=state.pr_url,
        worktree_path=state.worktree_path,
    )
    try:
        write_auto_publish_result.write_result_file(state.parent_repo, result)
    except OSError as exc:
        sys.stderr.write(f"WARNING: result.json 書き込みにも失敗: {exc}\n")
    sys.exit(1)


def finish(
    state: PublishState,
    *,
    worktree_removed: bool,
    worktree_remove_error: str | None = None,
) -> None:
    """status=ok の result.json を書き出す（成功経路）。"""
    result = write_auto_publish_result.build_result(
        status="ok",
        article_path=state.article_path,
        edit_url=state.edit_url,
        public_url=state.public_url,
        pr_url=state.pr_url,
        worktree_removed=worktree_removed,
        worktree_path=state.worktree_path,
        worktree_remove_error=worktree_remove_error,
    )
    try:
        write_auto_publish_result.write_result_file(state.parent_repo, result)
    except OSError as exc:
        sys.stderr.write(f"WARNING: result.json 書き込みに失敗: {exc}\n")


def derive_publish_urls(diary_date: str) -> tuple[str | None, str]:
    """published.jsonl と .env から、編集ページ URL と公開 URL を組み立てる.

    投稿（subprocess）成功後に呼ぶ。published.jsonl の当該日 `edit_url`（AtomPub URL）から
    ブラウザ編集 URL を、`diary_date` から公開 URL を生成する。

    Returns:
        (編集ページ URL or None, 公開 URL)
    """
    env = publish_hatena.load_env()
    hatena_id = publish_hatena.require_env(env, "HATENA_ID")
    blog_id = publish_hatena.require_env(env, "HATENA_BLOG_ID")
    public_url = publish_hatena.build_public_url(blog_id=blog_id, diary_date=diary_date)
    entry = publish_hatena.lookup_published(diary_date)
    atom_edit_url = entry["edit_url"] if entry else None
    edit_url = publish_hatena.build_browser_edit_url(
        atom_edit_url=atom_edit_url, hatena_id=hatena_id, blog_id=blog_id
    )
    return edit_url, public_url


# ---------------------------------------------------------------------------
# Phase 0: setup
# ---------------------------------------------------------------------------
def cmd_setup() -> int:
    parent_repo = _run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    if not parent_repo:
        sys.stderr.write("[PHASE environment] 失敗: git リポジトリ外で起動されました\n")
        return 1
    state = PublishState(parent_repo=parent_repo)

    # 前回残骸の result.json を削除する
    result_path = (
        pathlib.Path(parent_repo) / ".tmp" / "auto-publish-diary" / "result.json"
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.unlink(missing_ok=True)

    # 親リポからの起動を強制する（worktree 内からの起動は非対応）
    git_dir = _run(["git", "rev-parse", "--git-dir"]).stdout.strip()
    common_dir = _run(["git", "rev-parse", "--git-common-dir"]).stdout.strip()
    if os.path.realpath(git_dir) != os.path.realpath(common_dir):
        fail(state, failed_phase="environment", error="worktree 内からの起動は非対応")

    # 親リポ clean 確認
    if _run(["git", "-C", parent_repo, "status", "--porcelain"]).stdout.strip():
        fail(state, failed_phase="environment", error="親リポに未コミット変更があります")

    # main 最新化
    if _run(["git", "-C", parent_repo, "switch", "main"]).returncode != 0:
        fail(state, failed_phase="environment", error="git switch main に失敗")
    try:
        pull = _run(
            ["git", "-C", parent_repo, "pull", "--ff-only"],
            timeout=NETWORK_TIMEOUT,
            network=True,
        )
    except subprocess.TimeoutExpired:
        fail(state, failed_phase="environment", error="git pull --ff-only がタイムアウト（120 秒）")
    if pull.returncode != 0:
        fail(state, failed_phase="environment", error="git pull --ff-only に失敗")

    # ブランチ名・worktree パスを決定（実行日ベース）
    now = datetime.now()
    repo_name = os.path.basename(parent_repo)
    parent_dir = os.path.dirname(parent_repo)
    branch_name = f"auto/diary-{now.strftime('%Y-%m-%d')}"
    worktree_path = os.path.join(parent_dir, f"{repo_name}-wt-auto-{now.strftime('%Y%m%d')}")
    state.branch_name = branch_name

    # 同名ブランチ既存（同日二重実行）の事前検査
    if _run(
        ["git", "-C", parent_repo, "rev-parse", "--verify", f"refs/heads/{branch_name}"]
    ).returncode == 0:
        fail(state, failed_phase="environment", error=f"ブランチが既に存在: {branch_name}")

    # worktree 作成
    if _run(
        ["git", "-C", parent_repo, "worktree", "add", "-b", branch_name, worktree_path, "main"]
    ).returncode != 0:
        fail(state, failed_phase="environment", error=f"git worktree add に失敗: {worktree_path}")
    state.worktree_path = worktree_path

    # .env を worktree へコピー（.gitignore 対象でチェックアウトされないため）
    parent_env = pathlib.Path(parent_repo) / ".env"
    if not parent_env.exists():
        fail(state, failed_phase="environment", error=".env が見つかりません")
    worktree_env = pathlib.Path(worktree_path) / ".env"
    worktree_env.write_text(parent_env.read_text(encoding="utf-8"), encoding="utf-8")
    env_text = worktree_env.read_text(encoding="utf-8")
    if not any(line.startswith("HATENA_ID=") for line in env_text.splitlines()) or not any(
        line.startswith("HATENA_BLOG_ID=") for line in env_text.splitlines()
    ):
        fail(
            state,
            failed_phase="environment",
            error=".env に HATENA_ID または HATENA_BLOG_ID が未設定",
        )

    print("[PHASE environment] 完了")
    print(f"WORKTREE: {worktree_path}")
    print(f"BRANCH: {branch_name}")
    return 0


# ---------------------------------------------------------------------------
# Phase 2〜5: finalize
# ---------------------------------------------------------------------------
def _resolve_context() -> tuple[str, str, str]:
    """worktree 内から parent_repo / worktree_path / branch_name を git 経由で導出する。"""
    worktree_path = _run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    common_dir = _run(["git", "rev-parse", "--git-common-dir"]).stdout.strip()
    parent_repo = os.path.dirname(os.path.realpath(common_dir))
    branch_name = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    return parent_repo, worktree_path, branch_name


def cmd_finalize(article_path: str) -> int:
    parent_repo, worktree_path, branch_name = _resolve_context()
    state = PublishState(
        parent_repo=parent_repo,
        worktree_path=worktree_path,
        branch_name=branch_name,
    )

    # Phase 1（記事生成）の成否はここで判定する。article_path が空・不在なら write 失敗扱い
    if not article_path or not (pathlib.Path(worktree_path) / article_path).is_file():
        fail(state, failed_phase="write", error=f"記事生成に失敗（article-path: {article_path!r}）")
    state.article_path = article_path

    # フロントマターから日付・タイトルを取得（実行時刻でなく記事日付を使う）
    try:
        frontmatter, _body = publish_hatena.parse_article(
            pathlib.Path(worktree_path) / article_path
        )
    except SystemExit as exc:
        fail(state, failed_phase="git", error=f"フロントマター読取失敗: {exc}")
    article_date = frontmatter.get("date", "")
    article_title = frontmatter.get("title", "")
    if not article_date or not article_title:
        fail(state, failed_phase="git", error="フロントマター読取失敗（date または title が空）")

    # --- Phase 2: Hatena 下書き登録（subprocess）---
    try:
        publish = _run(
            [sys.executable, "scripts/publish_hatena.py", article_date],
            cwd=worktree_path,
            timeout=NETWORK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        fail(state, failed_phase="publish", error="publish_hatena.py がタイムアウト（120 秒）")
    if publish.returncode != 0:
        tail = (publish.stderr or "").strip().splitlines()
        detail = tail[-1] if tail else "(stderr 空)"
        fail(state, failed_phase="publish", error=f"publish_hatena.py exit {publish.returncode}: {detail}")

    # URL は stdout grep せず published.jsonl + 純粋関数で組み立てる。
    # load_env/require_env は SystemExit を投げうるため捕捉して fail() に合流させる
    # （result.json を必ず書く契約のため、未捕捉の SystemExit で素抜けさせない）
    try:
        edit_url, public_url = derive_publish_urls(article_date)
    except SystemExit as exc:
        fail(state, failed_phase="publish", error=f"URL 組み立て中の環境エラー: {exc}")
    if not edit_url:
        fail(
            state,
            failed_phase="publish",
            error="編集 URL を組み立てられず（published.jsonl の edit_url を確認）",
        )
    state.edit_url = edit_url
    state.public_url = public_url

    # --- Phase 3: git commit + push + PR + merge ---
    commit_msg = f"diary: {article_date} の日記を追加"
    if _run(["git", "-C", worktree_path, "add", "articles/hatena/"]).returncode != 0:
        fail(state, failed_phase="git", error="git add に失敗")
    if _run(["git", "-C", worktree_path, "commit", "-m", commit_msg]).returncode != 0:
        fail(state, failed_phase="git", error="git commit に失敗（変更がない等）")
    try:
        push = _run(
            ["git", "-C", worktree_path, "push", "-u", "origin", branch_name],
            timeout=NETWORK_TIMEOUT,
            network=True,
        )
    except subprocess.TimeoutExpired:
        fail(state, failed_phase="git", error="git push がタイムアウト（120 秒）")
    if push.returncode != 0:
        fail(state, failed_phase="git", error="git push に失敗")

    try:
        pr_body = build_pr_body(
            worktree_path,
            title=article_title,
            date=article_date,
            article_path=article_path,
            edit_url=edit_url,
            public_url=public_url,
        )
    except OSError as exc:
        fail(state, failed_phase="git", error=f"PR 本文テンプレの読み取りに失敗: {exc}")
    try:
        create = _run(
            [
                "gh", "pr", "create",
                "--base", "main",
                "--head", branch_name,
                "--title", commit_msg,
                "--body", pr_body,
            ],
            cwd=worktree_path,
            timeout=NETWORK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        fail(state, failed_phase="git", error="gh pr create がタイムアウト（120 秒）")
    if create.returncode != 0:
        fail(state, failed_phase="git", error=f"gh pr create に失敗: {(create.stderr or '').strip()}")
    pr_url = (create.stdout or "").strip().splitlines()[-1] if create.stdout.strip() else ""
    if "/pull/" not in pr_url:
        fail(state, failed_phase="git", error=f"gh pr create 出力から PR URL を抽出できず: {pr_url!r}")
    state.pr_url = pr_url
    pr_number = pr_url.rstrip("/").rsplit("/", 1)[-1]

    try:
        merge = _run(
            ["gh", "pr", "merge", pr_number, "--squash", "--admin"],
            cwd=worktree_path,
            timeout=NETWORK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        fail(state, failed_phase="git", error="gh pr merge がタイムアウト（120 秒）")
    if merge.returncode != 0:
        # ネットワーク一時失敗・将来的な `--delete-branch` 副作用等で「リモートはマージ済み
        # なのに exit 非 0」となるケースを救うため、リモートの実 state を 1 回だけ確認する
        # （#219）。
        merge_stderr = _summarize_stderr(merge.stderr) or "(stderr 空)"
        pr_state = _query_pr_state(pr_number, worktree_path)
        if pr_state == "MERGED":
            sys.stderr.write(
                f"WARNING: gh pr merge exit {merge.returncode} / state=MERGED で継続: "
                f"{merge_stderr}\n"
            )
        else:
            state_detail = f" / state={pr_state}" if pr_state else " / state 取得失敗"
            fail(
                state,
                failed_phase="git",
                error=f"gh pr merge に失敗: {merge_stderr}{state_detail}",
            )

    # --- Phase 4: worktree クリーンアップ（失敗しても status=ok）---
    worktree_removed, worktree_remove_error = cleanup(parent_repo, worktree_path, branch_name)

    # --- Phase 5: 成功 result.json ---
    finish(
        state,
        worktree_removed=worktree_removed,
        worktree_remove_error=worktree_remove_error,
    )
    if worktree_removed:
        if worktree_remove_error:
            print(
                f"✅ /auto-publish-diary 全工程成功（rmdir フォールバックで救済: {worktree_remove_error}）"
            )
        else:
            print("✅ /auto-publish-diary 全工程成功")
    else:
        detail = f" / stderr: {worktree_remove_error}" if worktree_remove_error else ""
        print(
            f"✅ /auto-publish-diary 全工程成功（worktree 削除のみ失敗: {worktree_path}{detail}）"
        )
    return 0


def build_pr_body(
    worktree_path: str,
    *,
    title: str,
    date: str,
    article_path: str,
    edit_url: str,
    public_url: str,
) -> str:
    """PR テンプレを読み、プレースホルダをリテラル置換した本文を返す.

    `str.replace` で置換するため、値に `&` `\\` `|` `$` 等が含まれてもリテラル扱いになる。
    """
    template_path = (
        pathlib.Path(worktree_path) / ".github" / "PULL_REQUEST_TEMPLATE" / "auto-diary.md"
    )
    body = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{TITLE}}": title,
        "{{DATE}}": date,
        "{{EDIT_URL}}": edit_url,
        "{{PUBLIC_URL}}": public_url,
        "{{ARTICLE_PATH}}": article_path,
    }
    for key, value in replacements.items():
        body = body.replace(key, value)
    return body


def cleanup(
    parent_repo: str, worktree_path: str, branch_name: str
) -> tuple[bool, str | None]:
    """worktree 削除・ローカルブランチ削除・親リポ main 同期。

    前提: `gh pr merge --squash --admin` が成功した直後に限定して呼び出すこと。
    未マージブランチに対して呼ぶと `git branch -D` で未マージ変更が失われる。

    Returns:
        (worktree 削除成否, `git worktree remove --force` の stderr 1 行要約).
        Windows で `git worktree remove --force` が rmdir 段階だけ Permission denied
        で失敗するケース（#245）に対し、ディレクトリが空であれば `os.rmdir` で
        フォールバックする。フォールバックで削除に成功した場合は第 1 戻り値を True
        にしつつ、第 2 戻り値には git の元 stderr を保持する（result.json で
        `worktree_removed=true` + `worktree_remove_error` 非 null の組み合わせを
        「rmdir フォールバック発動」のシグナルとして残し、根本原因の継続観測を可能にする）。
    """
    # finalize は worktree を cwd として起動される。Windows では cwd が worktree 内に
    # ある間はディレクトリを削除できないため、remove 前に親リポへ chdir して cwd ロックを
    # 解放する（git 呼び出し自体は -C で repo を指定済み。chdir は OS の cwd ロック対策）。
    os.chdir(parent_repo)
    remove_proc = _run(
        ["git", "-C", parent_repo, "worktree", "remove", "--force", worktree_path]
    )
    removed = remove_proc.returncode == 0
    remove_error = None if removed else _summarize_stderr(remove_proc.stderr)
    if not removed:
        try:
            if os.path.isdir(worktree_path) and not os.listdir(worktree_path):
                os.rmdir(worktree_path)
                removed = True
        except OSError as exc:
            sys.stderr.write(f"WARNING: rmdir fallback failed: {exc}\n")
    # squash マージ後は -d が「not fully merged」で失敗するため -D で強制削除する。
    # gh pr merge --admin --squash 成功直後に限定して呼ぶため安全。失敗は無視
    _run(["git", "-C", parent_repo, "branch", "-D", branch_name])
    # squash マージ済みコミットをローカル main へ取り込む（失敗は無視）
    try:
        _run(
            ["git", "-C", parent_repo, "pull", "--ff-only", "origin", "main"],
            timeout=NETWORK_TIMEOUT,
            network=True,
        )
    except subprocess.TimeoutExpired:
        pass
    return removed, remove_error


def _query_pr_state(pr_number: str, cwd: str) -> str | None:
    """`gh pr view <num> --json state --jq .state` を 1 回だけ呼んで state 文字列を返す。

    マージ判定の正確性向上のため、`gh pr merge` の exit code が非 0 のときの保険として
    リモート state を確認する用途（#219）。タイムアウト・取得失敗時は None を返す。

    cwd は worktree パスを渡す前提（gh のリポジトリ自動検出を利用するため）。worktree が
    壊れている等で gh 自身が exit 非 0 になった場合も None 返却で `fail()` 経路へ合流する。
    """
    try:
        view = _run(
            ["gh", "pr", "view", pr_number, "--json", "state", "--jq", ".state"],
            cwd=cwd,
            timeout=NETWORK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None
    if view.returncode != 0:
        return None
    return (view.stdout or "").strip() or None


def _summarize_stderr(stderr: str | None) -> str | None:
    """subprocess の stderr を result.json 用に 1 行要約にする。

    複数行を半角空白で連結し、前後の空白を除去する。空文字は None に正規化する。
    """
    if not stderr:
        return None
    summary = " ".join(stderr.split())
    return summary or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Phase 0: 環境準備・worktree 作成")
    p_fin = sub.add_parser("finalize", help="Phase 2〜5: 投稿・git・PR・merge・cleanup")
    p_fin.add_argument("--article-path", required=True, help="生成記事の worktree 相対パス")
    args = parser.parse_args(argv)

    if args.command == "setup":
        return cmd_setup()
    return cmd_finalize(args.article_path)


if __name__ == "__main__":
    sys.exit(main())
