"""はてなブログのエントリとローカル記事を削除する.

仕様: .claude/skills/delete-hatena/SKILL.md

本スクリプトは非対話的に動作する（呼ばれた時点で削除を実行する）。
削除前の対象確認は呼び出し元（`/delete-hatena` スキルから Claude が AskUserQuestion で実施する）に委譲し、
スクリプト単体実行時も明示的な呼び出しを意思表示と見なして即実行する。

処理:

1. 引数パース（単一日付 / 範囲 `YYYY-MM-DD..YYYY-MM-DD` / `--remote-only` / `--local-only`）
2. 対象リスト確定（単一は存在しなければエラー、範囲は存在しない日付をスキップ）
3. 各対象を順次削除
   - はてな AtomPub DELETE（`--local-only` 以外）
   - ローカル md 削除（`--remote-only` 以外）
   - published.jsonl 更新（デフォルト: 該当行物理削除 / `--remote-only`: edit_url を null 化）
4. 失敗時は即停止し、完了済み・未実行の内訳をサマリー表示

使用例:

    python scripts/delete_hatena.py 2026-05-13                          # 単一日付削除
    python scripts/delete_hatena.py 2026-05-01..2026-05-07              # 範囲削除
    python scripts/delete_hatena.py 2026-05-13 --remote-only            # はてな側のみ
    python scripts/delete_hatena.py 2026-05-13 --local-only             # ローカルのみ
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error

from publish_hatena import (
    ARTICLES_DIR,
    KEY_API_KEY,
    PUBLISHED_JSONL,
    REPO_ROOT,
    PublishedEntry,
    _atompub_request,
    get_secret,
    load_env,
    lookup_published,
    parse_article,
    require_env,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")


def parse_date_arg(arg: str) -> tuple[list[str], bool]:
    """日付引数（単一 or 範囲）を連続日付のリストに展開する.

    単一: `YYYY-MM-DD` → ([date], False)
    範囲: `YYYY-MM-DD..YYYY-MM-DD` → (連続日付のリスト, True)

    `is_range` は元の引数が範囲記法かどうかを表す。日数が 1 件でも、`..` 記法
    （例: `2026-05-13..2026-05-13`）なら True を返す。md 不在時のスキップ可否を
    判定するために要素数ではなく記法で判定する。

    単一・範囲どちらも `date.fromisoformat` で値域検証する。
    """
    if _DATE_RE.match(arg):
        try:
            dt.date.fromisoformat(arg)
        except ValueError as e:
            raise SystemExit(f"日付の値が不正です: {e}") from e
        return [arg], False
    m = _RANGE_RE.match(arg)
    if not m:
        raise SystemExit(
            f"日付の形式が不正です: {arg!r}\n"
            f"  単一: YYYY-MM-DD / 範囲: YYYY-MM-DD..YYYY-MM-DD"
        )
    start_str, end_str = m.group(1), m.group(2)
    try:
        start = dt.date.fromisoformat(start_str)
        end = dt.date.fromisoformat(end_str)
    except ValueError as e:
        raise SystemExit(f"日付の値が不正です: {e}") from e
    if start > end:
        raise SystemExit(
            f"範囲指定で開始日が終了日より後ろです: {start_str}..{end_str}"
        )
    dates: list[str] = []
    cur = start
    while cur <= end:
        dates.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return dates, True


def article_path_for(date: str) -> pathlib.Path:
    return ARTICLES_DIR / f"{date}-diary.md"


def delete_remote_entry(
    *,
    edit_url: str,
    hatena_id: str,
    api_key: str,
) -> None:
    """AtomPub DELETE を実行する.

    Raises:
        RuntimeError: 以下のいずれかが発生した場合（即停止のため呼び出し側で捕捉）
            - HTTP 404（はてな側にエントリ不在）
            - 上記以外の HTTPError（401/403/409/5xx 等）
            - ネットワーク失敗（urllib.error.URLError / TimeoutError）
            - 2xx 応答だが status が 200/204 以外
    """
    try:
        status, _body = _atompub_request(
            method="DELETE",
            url=edit_url,
            hatena_id=hatena_id,
            api_key=api_key,
        )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                f"はてな側にエントリが見つかりません (HTTP 404): {edit_url}\n"
                f"  管理画面で既に削除済みの可能性があります。\n"
                f"  published.jsonl の edit_url を確認してください。"
            ) from e
        raise RuntimeError(f"DELETE 失敗 (HTTP {e.code}): {edit_url}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"DELETE ネットワークエラー: {e}") from e
    if status not in (200, 204):
        raise RuntimeError(f"DELETE 失敗 (HTTP {status}): {edit_url}")


def rewrite_published_jsonl(
    *,
    remove_dates: set[str],
    nullify_dates: set[str],
) -> None:
    """published.jsonl を一括書き換える.

    `remove_dates` の日付エントリは行ごと削除し、
    `nullify_dates` の日付エントリは edit_url を null に更新する。
    壊れた JSON 行・空行・対象外の日付の行は元のまま保持する。

    atomic rename で書き込み途中の中断に備える。
    """
    if not PUBLISHED_JSONL.exists():
        return
    text = PUBLISHED_JSONL.read_text(encoding="utf-8")
    out_lines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            out_lines.append(line)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        date = obj.get("date")
        if date in remove_dates:
            continue
        if date in nullify_dates:
            obj["edit_url"] = None
            out_lines.append(json.dumps(obj, ensure_ascii=False))
            continue
        out_lines.append(line)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".published.jsonl.", dir=PUBLISHED_JSONL.parent
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")
        os.replace(tmp_path, PUBLISHED_JSONL)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class Target:
    """削除対象 1 件分の情報."""

    def __init__(
        self,
        *,
        date: str,
        article_path: pathlib.Path,
        title: str,
        entry: PublishedEntry | None,
    ) -> None:
        self.date = date
        self.article_path = article_path
        self.title = title
        self.entry = entry  # published.jsonl のエントリ（無い場合 None）

    @property
    def edit_url(self) -> str | None:
        return self.entry["edit_url"] if self.entry else None


def build_targets(dates: list[str], *, is_range: bool) -> tuple[list[Target], list[str]]:
    """日付リストを Target リストに変換する.

    Returns:
        (targets, skipped_dates)
        - targets: 対象 md が存在する日付のリスト
        - skipped_dates: 対象 md が存在しない日付（範囲モードのみスキップ、単一は呼び出し側で停止）
    """
    targets: list[Target] = []
    skipped: list[str] = []
    for date in dates:
        path = article_path_for(date)
        if not path.exists():
            if is_range:
                skipped.append(date)
                continue
            raise SystemExit(
                f"対象記事が見つかりません: {path.relative_to(REPO_ROOT)}"
            )
        frontmatter, _body = parse_article(path)
        title = frontmatter.get("title", "")
        entry = lookup_published(date)
        targets.append(Target(date=date, article_path=path, title=title, entry=entry))
    return targets, skipped


def print_target_table(targets: list[Target]) -> None:
    """対象一覧を画面表示する."""
    print("削除対象:", file=sys.stderr)
    for t in targets:
        edit_status = "edit_url: あり" if t.edit_url else "edit_url: なし"
        print(
            f"  - {t.date}  {t.title}  ({edit_status})",
            file=sys.stderr,
        )


def validate_targets_for_mode(
    targets: list[Target],
    *,
    remote_only: bool,
) -> None:
    """モードに応じた対象の事前検証.

    `--remote-only` 時、はてな DELETE 対象がない（全エントリの edit_url が null / 未登録）
    場合はエラー停止する（実行しても何も起きないため）。
    """
    if not remote_only:
        return
    no_edit_url = [t for t in targets if t.edit_url is None]
    if no_edit_url:
        dates = ", ".join(t.date for t in no_edit_url)
        raise SystemExit(
            f"❌ --remote-only 指定ですが、以下の日付のエントリは edit_url が記録されていません: {dates}\n"
            f"  はてな側 DELETE 対象が存在しないため停止します。"
        )


@dataclasses.dataclass
class ProcessResult:
    """1 対象の削除処理結果と段階別完了状態.

    remote_attempted: はてな側 DELETE を試行したか（`--local-only` か edit_url 未登録なら False）
    remote_done: はてな側 DELETE が成功したか
    local_attempted: ローカル md 削除を試行したか（`--remote-only` なら False）
    local_done: ローカル md 削除が成功したか
    error: 失敗時のエラー内容（成功時 None）

    jsonl 更新は process_targets の最後に一括で行うため、本クラスでは追跡しない。
    失敗対象の jsonl は反映されないが、それまで成功した対象の jsonl は反映される。
    """

    date: str
    remote_attempted: bool = False
    remote_done: bool = False
    local_attempted: bool = False
    local_done: bool = False
    error: str | None = None


def process_targets(
    targets: list[Target],
    *,
    remote_only: bool,
    local_only: bool,
    hatena_id: str,
    api_key: str,
) -> tuple[list[ProcessResult], list[str], str | None]:
    """対象を順次削除する.

    Returns:
        (results, pending_dates, error_message)
        - results: 実行した（試行中に失敗した含む）対象の処理結果リスト。各 ProcessResult が段階別完了状態を保持
        - pending_dates: 失敗で停止した場合の未実行の日付（results に含まれない残り）
        - error_message: 失敗時のエラー内容（成功時 None）
    """
    results: list[ProcessResult] = []
    remove_dates: set[str] = set()
    nullify_dates: set[str] = set()
    for i, t in enumerate(targets):
        result = ProcessResult(date=t.date)
        results.append(result)
        try:
            print(f"🗑️ {t.date} 削除中...", file=sys.stderr)
            if not local_only:
                if t.edit_url is not None:
                    result.remote_attempted = True
                    delete_remote_entry(
                        edit_url=t.edit_url,
                        hatena_id=hatena_id,
                        api_key=api_key,
                    )
                    result.remote_done = True
                    print("  はてな側 DELETE 成功", file=sys.stderr)
                else:
                    print(
                        "  はてな側 DELETE スキップ（edit_url 未登録）",
                        file=sys.stderr,
                    )
            if not remote_only:
                result.local_attempted = True
                t.article_path.unlink()
                result.local_done = True
                print(
                    f"  ローカル md 削除: {t.article_path.relative_to(REPO_ROOT)}",
                    file=sys.stderr,
                )
            if remote_only:
                if t.entry is not None:
                    nullify_dates.add(t.date)
            else:
                if t.entry is not None:
                    remove_dates.add(t.date)
        except (RuntimeError, OSError) as e:
            result.error = str(e)
            jsonl_error = _safe_rewrite_published_jsonl(remove_dates, nullify_dates)
            pending = [u.date for u in targets[i + 1:]]
            error_msg = str(e)
            if jsonl_error is not None:
                error_msg = f"{error_msg} / さらに jsonl 書き換えも失敗: {jsonl_error}"
            return results, pending, error_msg
    jsonl_error = _safe_rewrite_published_jsonl(remove_dates, nullify_dates)
    if jsonl_error is not None:
        return results, [], f"jsonl 書き換え失敗: {jsonl_error}"
    return results, [], None


def _safe_rewrite_published_jsonl(
    remove_dates: set[str], nullify_dates: set[str]
) -> str | None:
    """rewrite_published_jsonl を OSError を捕捉して呼び出す.

    Returns:
        失敗時はエラーメッセージ、成功時 None
    """
    try:
        rewrite_published_jsonl(
            remove_dates=remove_dates, nullify_dates=nullify_dates
        )
    except OSError as e:
        return str(e)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="はてなブログのエントリとローカル記事を削除する",
    )
    parser.add_argument(
        "date",
        help="削除対象の日付。単一: YYYY-MM-DD / 範囲: YYYY-MM-DD..YYYY-MM-DD",
    )
    parser.add_argument(
        "--remote-only",
        action="store_true",
        help="はてな側 DELETE のみ実行し、ローカル md は残す（jsonl の edit_url を null 化）",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="ローカル md 削除と jsonl 行削除のみ実行し、はてな側は呼ばない",
    )
    args = parser.parse_args(argv)

    if args.remote_only and args.local_only:
        print(
            "❌ --remote-only と --local-only は同時に指定できません",
            file=sys.stderr,
        )
        return 1

    dates, is_range = parse_date_arg(args.date)
    targets, skipped = build_targets(dates, is_range=is_range)

    if skipped:
        print(
            f"⏭️ スキップ（対象 md が存在しない）: {', '.join(skipped)}",
            file=sys.stderr,
        )
    if not targets:
        print(
            "❌ 削除対象が 0 件です（範囲内の全日付で md が存在しません）",
            file=sys.stderr,
        )
        return 1

    validate_targets_for_mode(targets, remote_only=args.remote_only)

    print_target_table(targets)

    mode_label = (
        "はてな側のみ"
        if args.remote_only
        else "ローカルのみ"
        if args.local_only
        else "ローカル + はてな + jsonl"
    )
    print(f"モード: {mode_label}（対象 {len(targets)} 件）", file=sys.stderr)

    if args.local_only:
        hatena_id = ""
        api_key = ""
    else:
        env = load_env()
        hatena_id = require_env(env, "HATENA_ID")
        api_key = get_secret(KEY_API_KEY)

    results, pending, error_msg = process_targets(
        targets,
        remote_only=args.remote_only,
        local_only=args.local_only,
        hatena_id=hatena_id,
        api_key=api_key,
    )

    completed_results = [r for r in results if r.error is None]
    failed_result = next((r for r in results if r.error is not None), None)

    print("", file=sys.stderr)
    print(f"完了: {len(completed_results)} 件", file=sys.stderr)
    if completed_results:
        print(f"  {', '.join(r.date for r in completed_results)}", file=sys.stderr)
    if failed_result is not None:
        print(f"❌ 失敗で停止: {failed_result.date}", file=sys.stderr)
        print(
            f"  はてな側 DELETE: "
            f"{'✓ 完了済み' if failed_result.remote_done else '✗ 未完了' if failed_result.remote_attempted else '- 試行せず'}",
            file=sys.stderr,
        )
        print(
            f"  ローカル md 削除: "
            f"{'✓ 完了済み' if failed_result.local_done else '✗ 未完了' if failed_result.local_attempted else '- 試行せず'}",
            file=sys.stderr,
        )
        print(
            "  jsonl 更新: 失敗対象は未反映（完了済み対象のみ反映済み）",
            file=sys.stderr,
        )
        print(f"  エラー: {error_msg}", file=sys.stderr)
        if pending:
            print(f"未実行 ({len(pending)} 件): {', '.join(pending)}", file=sys.stderr)
        return 1
    print("✅ 全件削除成功", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
