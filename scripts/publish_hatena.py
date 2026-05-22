"""生成済みの日記記事を AtomPub で下書きとして投稿する.

仕様: .claude/skills/publish-hatena/SKILL.md

処理:

1. 対象記事を選択（引数: 日付 YYYY-MM-DD、未指定時は最新ファイル）
2. articles/hatena/published.jsonl から同日付エントリを検索（edit_url 付き / edit_url 欠落 / 未登録 の 3 状態）
3. --force なし & 既存ありなら停止、--force あり & 未登録または edit_url 欠落なら停止
4. フロントマター（title / date / category）を解析、本文を取得
5. リポジトリルートの .env から HATENA_ID / HATENA_BLOG_ID を取得
6. keyring から HATENA_API_KEY を取得（service="article-writer"）
7. --force 時のみ: edit_url に対して GET し、レスポンスの `<app:control>/<app:draft>` 値（yes / no）を取得する
8. AtomPub Atom Entry XML を組み立て（`<title>` / `<updated>` / `<content type="text/x-markdown">` / `<app:draft>` は POST 時 `yes` 固定、PUT 時はステップ 7 で取得した値を明示送信 / `<category>`）
9. Basic 認証で --force なしは POST、--force ありは既存 edit_url へ PUT
10. POST 成功時 published.jsonl に 1 行 JSON を追記、PUT 成功時は title を最新タイトルに更新（edit_url 保持）

使用例:

    python scripts/publish_hatena.py              # 最新の記事を下書き登録（POST）
    python scripts/publish_hatena.py 2026-05-13   # 指定日付の記事を下書き登録（POST）
    python scripts/publish_hatena.py --force      # 同日エントリを PUT で更新
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import TypedDict

import keyring

import convert_article_html

SERVICE = "article-writer"
KEY_API_KEY = "HATENA_API_KEY"


class PublishedEntry(TypedDict):
    date: str
    title: str
    edit_url: str | None


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ARTICLES_DIR = REPO_ROOT / "articles" / "hatena"
PUBLISHED_JSONL = ARTICLES_DIR / "published.jsonl"


def load_env() -> dict[str, str]:
    """`.env` を読み込んで dict として返す.

    `KEY=value` 形式の各行をパースする。クォート文字列（`"..."` または `'...'`）の
    場合はクォート内をそのまま値とする。非クォート値は `#` 以降を行末コメントとして
    切り落とす（例: `KEY=value # コメント` → 値は `value`）。
    値内に `#` を含めたい場合はクォートで囲む。
    """
    if not ENV_FILE.exists():
        msg = (
            f".env が見つかりません: {ENV_FILE}\n"
            f"以下を記載してください（公開情報・git ignore 済み）:\n"
            f"  HATENA_ID=<はてなID>\n"
            f"  HATENA_BLOG_ID=<ブログのホスト名>"
        )
        raise SystemExit(msg)
    result: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
            value = raw[1:-1]
        elif "#" in raw:
            value = raw.split("#", 1)[0].rstrip()
        else:
            value = raw
        result[key.strip()] = value
    return result


def require_env(env: dict[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise SystemExit(f".env に未設定: {key}")
    return value


def get_secret(key: str) -> str:
    value = keyring.get_password(SERVICE, key)
    if value is None:
        msg = (
            f"keyring に未登録: service={SERVICE!r}, key={key!r}\n"
            f"以下のコマンドで対話入力で登録してください（シェル履歴に値を残さないため getpass を使用）:\n"
            f"  python -c \"import keyring, getpass; "
            f"keyring.set_password('{SERVICE}', '{key}', getpass.getpass('value: '))\""
        )
        raise SystemExit(msg)
    return value


_ARTICLE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-diary\.md$")


def select_article(date: str | None) -> pathlib.Path:
    """対象記事を選ぶ. date 指定時は前方一致、未指定時はファイル名順で最新.

    ファイル名は `YYYY-MM-DD-diary.md` 形式（write-hatena-diary 仕様）のため、
    辞書順ソートで日付順になる。

    日付プレフィックスを持たない補助ファイル（README.md 等）は候補から除外する。

    ファイル名の `\\d{4}-\\d{2}-\\d{2}` は形式のみ検証し、年月日の値域（例: 2026-99-99）は検証しない。
    frontmatter `date:` も `main()` 側で同様に形式のみ検証する仕様（値域検証は AtomPub 側の解釈に委ねる）。
    """
    if not ARTICLES_DIR.exists():
        raise SystemExit(f"記事ディレクトリが存在しません: {ARTICLES_DIR}")
    # `*.md` glob で OS 側に拡張子フィルタを掛けて候補を絞り、正規表現で `YYYY-MM-DD-diary.md` 形式を確定する
    candidates = sorted(
        p for p in ARTICLES_DIR.glob("*.md") if _ARTICLE_NAME_RE.match(p.name)
    )
    if not candidates:
        raise SystemExit(
            f"対象記事がありません: {ARTICLES_DIR.as_posix()}/YYYY-MM-DD-diary.md"
        )
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise SystemExit(f"日付形式が不正です（YYYY-MM-DD で指定）: '{date}'")
        matched = [p for p in candidates if p.name.startswith(date)]
        if not matched:
            raise SystemExit(f"日付 {date} に対応する記事がありません: {ARTICLES_DIR.as_posix()}")
        return matched[-1]
    return candidates[-1]


def parse_article(path: pathlib.Path) -> tuple[dict[str, str], str]:
    """フロントマター（YAML 風 key: value）と本文を分離する."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", text, re.DOTALL)
    if not m:
        raise SystemExit(f"フロントマターが見つかりません: {path}")
    fm_text, body = m.group(1), m.group(2).lstrip("\r\n")
    frontmatter: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        frontmatter[k.strip()] = v.strip().strip('"').strip("'")
    for required in ("title", "date"):
        if required not in frontmatter:
            raise SystemExit(f"フロントマター '{required}' が未設定: {path}")
    return frontmatter, body


def strip_leading_h1(body: str, title: str) -> str:
    """本文先頭が `# <title>` の場合は剥がす（はてなブログはエントリ title を別管理するため）.

    `## title` や `# # title` のような重複 `#` は H1 と扱わない。
    """
    lines = body.splitlines(keepends=True)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines):
        stripped = lines[i].lstrip()
        # `# ` で始まり、3 文字目以降が `#` でない（= H1 のみ）
        if (
            stripped.startswith("# ")
            and (len(stripped) <= 2 or stripped[2] != "#")
        ):
            h1 = stripped[2:].rstrip("\r\n").strip()
            if h1 == title:
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                return "".join(lines[i:])
    return body


def parse_published() -> list[PublishedEntry]:
    """published.jsonl のデータ行を辞書のリストとして返す.

    各行は `{"date": "...", "title": "...", "edit_url": "..." or null}` 形式の JSON。
    空行・JSON パース失敗行・必須キー欠落行はスキップする。
    """
    if not PUBLISHED_JSONL.exists():
        return []
    entries: list[PublishedEntry] = []
    for line in PUBLISHED_JSONL.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        date = obj.get("date")
        title = obj.get("title")
        if not isinstance(date, str) or not isinstance(title, str):
            continue
        edit_url = obj.get("edit_url")
        if edit_url is not None and not isinstance(edit_url, str):
            edit_url = None
        entries.append({"date": date, "title": title, "edit_url": edit_url})
    return entries


def lookup_published(diary_date: str) -> PublishedEntry | None:
    """published.jsonl 内で指定日付のエントリを返す. 無ければ None."""
    for entry in parse_published():
        if entry["date"] == diary_date:
            return entry
    return None


def build_atom_entry(
    *,
    title: str,
    body: str,
    category: str | None,
    draft: bool,
    published_iso: str | None = None,
) -> bytes:
    """AtomPub Atom Entry XML を組み立てる.

    `<content type="text/x-markdown">` で Markdown を直接送信する。
    `draft` が `True`/`False` のとき `<app:draft>yes/no</app:draft>` を明示送信して
    下書き/公開を切り替える。はてな AtomPub 公式仕様では `<app:draft>` を省略すると
    「下書きでない」と判定される（= 公開化）ため、PUT 更新で既存の下書き状態を保持したい
    場合は事前に GET で取得した draft 値をそのまま渡すこと（fetch_entry_draft_status 参照）。
    `published_iso` が指定された場合は `<updated>` 要素を出力し、はてなブログの
    公開日時としてその値を使う（下書き状態でも公開時に指定日時で表示される）。
    """
    root = ET.Element(
        "entry",
        {
            "xmlns": "http://www.w3.org/2005/Atom",
            "xmlns:app": "http://www.w3.org/2007/app",
        },
    )
    ET.SubElement(root, "title").text = title
    if published_iso:
        ET.SubElement(root, "updated").text = published_iso
    ET.SubElement(root, "content", {"type": "text/x-markdown"}).text = body
    if category:
        ET.SubElement(root, "category", {"term": category})
    control = ET.SubElement(root, "app:control")
    ET.SubElement(control, "app:draft").text = "yes" if draft else "no"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def fetch_entry_draft_status(
    *,
    edit_url: str,
    hatena_id: str,
    api_key: str,
) -> bool:
    """既存エントリの draft 状態を GET で取得する.

    はてな AtomPub 公式仕様では PUT 時に `<app:draft>` を省略すると公開扱いになるため、
    PUT 前にこの関数で現状を取得し、build_atom_entry に同じ値を渡して状態を維持する。

    Returns:
        True (下書き) / False (公開)
    Raises:
        RuntimeError: HTTP エラー、ネットワーク失敗、XML パース失敗、
            `<app:control>/<app:draft>` 要素不在のいずれか
    """
    try:
        _status, body = _atompub_request(
            method="GET",
            url=edit_url,
            hatena_id=hatena_id,
            api_key=api_key,
        )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GET 失敗 (HTTP {exc.code}): {edit_url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"GET ネットワークエラー: {exc}") from exc

    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "app": "http://www.w3.org/2007/app",
    }
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError(f"GET レスポンス XML パース失敗: {exc}") from exc

    control_elem = root.find("app:control", namespaces)
    if control_elem is None:
        raise RuntimeError(
            "GET レスポンスに app:control 要素が見つかりません"
        )
    draft_elem = control_elem.find("app:draft", namespaces)
    if draft_elem is None:
        raise RuntimeError(
            "GET レスポンスに app:control/app:draft 要素が見つかりません"
        )
    if draft_elem.text is None or draft_elem.text.strip() == "":
        raise RuntimeError(
            "GET レスポンスの app:control/app:draft 要素にテキスト値がありません"
        )
    draft_text = draft_elem.text.strip().lower()
    if draft_text not in ("yes", "no"):
        raise RuntimeError(
            f"GET レスポンスの app:draft 値が想定外です: '{draft_elem.text}'"
            " (yes / no のみ受け付ける)"
        )
    return draft_text == "yes"


def basic_auth_header(hatena_id: str, api_key: str) -> str:
    token = base64.b64encode(f"{hatena_id}:{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _atompub_request(
    *,
    method: str,
    url: str,
    hatena_id: str,
    api_key: str,
    payload: bytes | None = None,
) -> tuple[int, bytes]:
    """AtomPub への HTTP リクエスト送信の共通実装.

    Basic 認証ヘッダ・Content-Type ヘッダ（payload あり時のみ）・タイムアウト（30 秒）を
    一元管理する。送信成功時は (HTTP status, レスポンスボディ bytes) を返す。
    ネットワーク失敗系の例外はそのまま raise し、呼び出し側でモード別に変換する
    （`send_entry` は -1/status コードへ、`fetch_entry_draft_status` は `RuntimeError` へ）。

    Raises:
        urllib.error.HTTPError, urllib.error.URLError, TimeoutError
    """
    headers = {"Authorization": basic_auth_header(hatena_id, api_key)}
    if payload is not None:
        headers["Content-Type"] = "application/atom+xml; charset=utf-8"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read()


def send_entry(
    *,
    method: str,
    url: str,
    hatena_id: str,
    api_key: str,
    payload: bytes,
) -> tuple[int, str]:
    """AtomPub に POST または PUT を送信する.

    戻り値の HTTP status はネットワーク失敗時 -1 を返す（HTTP ステータスと識別可能にするため）。
    呼び出し元は 200/201 以外を全て失敗として扱う。
    """
    try:
        status, body = _atompub_request(
            method=method,
            url=url,
            hatena_id=hatena_id,
            api_key=api_key,
            payload=payload,
        )
        return status, body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # HTTPError は URLError のサブクラスのため先に捕捉する
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except (urllib.error.URLError, TimeoutError) as e:
        return -1, f"network error: {e}"


def post_entry(
    *,
    hatena_id: str,
    blog_id: str,
    api_key: str,
    payload: bytes,
) -> tuple[int, str]:
    url = f"https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/atom/entry"
    return send_entry(
        method="POST",
        url=url,
        hatena_id=hatena_id,
        api_key=api_key,
        payload=payload,
    )


def put_entry(
    *,
    edit_url: str,
    hatena_id: str,
    api_key: str,
    payload: bytes,
) -> tuple[int, str]:
    return send_entry(
        method="PUT",
        url=edit_url,
        hatena_id=hatena_id,
        api_key=api_key,
        payload=payload,
    )


def extract_entry_id(response_body: str) -> str | None:
    try:
        root = ET.fromstring(response_body)
    except ET.ParseError:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    elem = root.find("atom:id", ns)
    return elem.text if elem is not None else None


def extract_link_href(response_body: str, *, rel: str) -> str | None:
    """レスポンスから指定 rel の link href を取り出す.

    rel="alternate" は人間向けの公開閲覧 URL、rel="edit" は AtomPub の PUT 用 URL。
    """
    try:
        root = ET.fromstring(response_body)
    except ET.ParseError:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for link in root.findall("atom:link", ns):
        if link.get("rel") == rel:
            return link.get("href")
    return None


def append_published(diary_date: str, title: str, edit_url: str | None) -> None:
    """published.jsonl に 1 行 JSON を追記する.

    日付欄は記事フロントマターの `date:` をそのまま使う（日記対象日）。
    edit_url が None なら `"edit_url": null` で出力する。
    日本語を `\\uXXXX` エスケープせず人間可読のまま保存するため ensure_ascii=False を指定する。
    """
    record = {"date": diary_date, "title": title, "edit_url": edit_url}
    line = json.dumps(record, ensure_ascii=False) + "\n"
    PUBLISHED_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISHED_JSONL.open("a", encoding="utf-8") as f:
        f.write(line)


def update_published_title(diary_date: str, title: str) -> bool:
    """published.jsonl 内の指定日付エントリの title を最新タイトルに更新する.

    PUT (--force) 時に最新タイトルへ追従させるため使用する。
    edit_url は既存値を保持する。

    壊れた JSON 行・空行は変更せずそのまま保持する（他行への影響を避ける）。

    Returns:
        True: 該当エントリが見つかり更新成功
        False: 該当エントリが見つからない / ファイル不在 / I/O 失敗

    I/O 失敗時（権限不足・ディスクフル等）は警告を stderr に出力し False を返す。
    """
    if not PUBLISHED_JSONL.exists():
        return False
    try:
        text = PUBLISHED_JSONL.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  ⚠️ published.jsonl の読み取りに失敗: {e}", file=sys.stderr)
        return False
    lines = text.splitlines()
    updated = False
    out_lines: list[str] = []
    for line in lines:
        if not line.strip():
            out_lines.append(line)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if obj.get("date") == diary_date:
            obj["title"] = title
            line = json.dumps(obj, ensure_ascii=False)
            updated = True
        out_lines.append(line)
    if updated:
        # 同一ディレクトリのテンポラリファイルに書き出してから atomic rename で置き換える。
        # 書き込み途中のプロセス中断・ディスクフル等でも、元ファイルの完全性を保つ。
        try:
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
        except OSError as e:
            print(f"  ⚠️ published.jsonl の書き込みに失敗: {e}", file=sys.stderr)
            return False
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成済みの日記記事を AtomPub で下書き登録する",
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="対象記事の日付（YYYY-MM-DD）。未指定時は最新の記事ファイル",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="published.jsonl 記録済みエントリの edit_url へ PUT で上書き更新する（新規投稿には使えない）",
    )
    args = parser.parse_args(argv)

    article_path = select_article(args.date)
    print(f"📄 対象記事: {article_path.relative_to(REPO_ROOT)}", file=sys.stderr)

    frontmatter, body = parse_article(article_path)
    title = frontmatter["title"]
    diary_date = frontmatter["date"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", diary_date):
        raise SystemExit(
            f"フロントマターの date が YYYY-MM-DD 形式ではありません: {diary_date!r}\n"
            f"  対象記事: {article_path}"
        )
    category = frontmatter.get("category")
    body = strip_leading_h1(body, title)
    try:
        body = convert_article_html.convert(body)
    except convert_article_html.ConvertError as e:
        raise SystemExit(f"❌ 記事本文の簡素記法変換に失敗: {e}") from e

    existing = lookup_published(diary_date)
    if args.force:
        if existing is None:
            msg = (
                f"⚠️ --force 指定ですが、{diary_date} のエントリが "
                f"{PUBLISHED_JSONL.relative_to(REPO_ROOT)} に登録されていません。\n"
                f"  --force は PUT で既存エントリを更新する動作のため、新規投稿には使えません。\n"
                f"  新規投稿する場合は --force を外して再実行してください。"
            )
            print(msg, file=sys.stderr)
            return 1
        if existing["edit_url"] is None:
            msg = (
                f"⚠️ --force 指定ですが、{diary_date} のエントリに edit_url が記録されていません。\n"
                f"  以下の手順で edit_url を {PUBLISHED_JSONL.relative_to(REPO_ROOT)} に手動追記してから再実行してください:\n"
                f"  1. はてなブログ管理画面で対象記事を開き、AtomPub edit URL を確認する\n"
                f"     URL 形式: https://blog.hatena.ne.jp/<HATENA_ID>/<HATENA_BLOG_ID>/atom/entry/<entry_id_part>\n"
                f"  2. 該当行の \"edit_url\" を null から URL 文字列に書き換える"
            )
            print(msg, file=sys.stderr)
            return 1
    elif existing is not None:
        msg = (
            f"⚠️ 同じ日付 ({diary_date}) のエントリが既に "
            f"{PUBLISHED_JSONL.relative_to(REPO_ROOT)} にあります\n"
            f"  再投稿する場合は --force で再実行する"
        )
        print(msg, file=sys.stderr)
        return 1

    env = load_env()
    hatena_id = require_env(env, "HATENA_ID")
    blog_id = require_env(env, "HATENA_BLOG_ID")
    api_key = get_secret(KEY_API_KEY)

    # フロントマター `date:` を JST 0 時として AtomPub `<updated>` にマップする。
    # 公開時にこの日時が記事の公開日として表示される。
    published_iso = f"{diary_date}T00:00:00+09:00"

    # PUT (--force) では事前に GET で既存の draft 状態を取得し、同じ値を明示送信して
    # 公開状態を維持する。はてな AtomPub 公式仕様で `<app:draft>` を省略すると
    # 公開扱いになるため、明示が必須。
    # POST (新規) は下書き登録のため draft=True。
    if args.force:
        assert existing is not None
        target_edit_url = existing["edit_url"]
        assert target_edit_url is not None
        print("🔍 既存の draft 状態を取得中...", file=sys.stderr)
        try:
            current_draft = fetch_entry_draft_status(
                edit_url=target_edit_url,
                hatena_id=hatena_id,
                api_key=api_key,
            )
        except RuntimeError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        state_label = "下書き" if current_draft else "公開"
        print(f"  現在の状態: {state_label}", file=sys.stderr)
        draft_value: bool = current_draft
    else:
        draft_value = True

    payload = build_atom_entry(
        title=title,
        body=body,
        category=category,
        draft=draft_value,
        published_iso=published_iso,
    )

    if args.force:
        print(f"🔄 PUT 中 (title: {title})", file=sys.stderr)
        status, response = put_entry(
            edit_url=target_edit_url,
            hatena_id=hatena_id,
            api_key=api_key,
            payload=payload,
        )
        op_label = f"更新成功（{state_label}状態を維持）"
    else:
        print(f"📤 POST 中 (title: {title})", file=sys.stderr)
        status, response = post_entry(
            hatena_id=hatena_id,
            blog_id=blog_id,
            api_key=api_key,
            payload=payload,
        )
        op_label = "下書き登録成功"

    if status not in (200, 201):
        if status == -1:
            print(f"❌ ネットワークエラー: {response}", file=sys.stderr)
            print("  少し時間を置いてから再実行する", file=sys.stderr)
        else:
            print(f"❌ HTTP {status}", file=sys.stderr)
            print(response, file=sys.stderr)
        return 1

    entry_id = extract_entry_id(response)
    public_url = extract_link_href(response, rel="alternate")
    edit_url = extract_link_href(response, rel="edit")
    print(f"✅ {op_label}")
    print(f"  記事: {article_path.relative_to(REPO_ROOT)}")
    print(f"  Entry ID: {entry_id if entry_id else '(取得失敗・管理画面で確認)'}")
    if public_url:
        print(f"  URL: {public_url}")

    append_failed = False
    if args.force:
        if update_published_title(diary_date, title):
            print("  published.jsonl の title を最新タイトルに更新（edit_url は保持）")
        else:
            print(
                "  ⚠️ published.jsonl の title 更新に失敗しました（該当エントリ未発見または I/O 失敗）",
                file=sys.stderr,
            )
            append_failed = True
    else:
        try:
            append_published(diary_date, title, edit_url)
            if edit_url:
                print("  published.jsonl に追記済み（edit_url 含む）")
            else:
                print(
                    "  ⚠️ レスポンスから edit_url を取得できませんでした。"
                    " published.jsonl には \"edit_url\": null で追記しました。\n"
                    f"  次回 --force で更新する前に、{PUBLISHED_JSONL.relative_to(REPO_ROOT)} の該当行の edit_url を URL 文字列に書き換えてください。",
                    file=sys.stderr,
                )
        except OSError as e:
            append_failed = True
            record = {"date": diary_date, "title": title, "edit_url": edit_url}
            line = json.dumps(record, ensure_ascii=False)
            print(
                f"  ⚠️ published.jsonl 追記に失敗: {e}\n"
                f"  以下の行を {PUBLISHED_JSONL.relative_to(REPO_ROOT)} に追記する:\n"
                f"    {line}",
                file=sys.stderr,
            )

    print(f"  管理画面: https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/edit")
    return 1 if append_failed else 0


if __name__ == "__main__":
    sys.exit(main())
