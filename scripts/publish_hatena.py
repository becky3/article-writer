"""生成済みの日記記事を AtomPub で下書きとして投稿する.

仕様: .claude/skills/publish-hatena/SKILL.md

処理:

1. 対象記事を選択（引数: 日付 YYYY-MM-DD、未指定時は最新ファイル）
2. articles/hatena/published.jsonl から同日付エントリを検索（edit_url 付き / edit_url 欠落 / 未登録 の 3 状態）
3. --force なし & 既存ありなら停止、--force あり & 未登録または edit_url 欠落なら停止
4. フロントマター（title / date / category）を解析、本文を取得
5. リポジトリルートの .env から HATENA_ID / HATENA_BLOG_ID を取得
6. keyring から HATENA_API_KEY を取得（service="article-writer"）
7. AtomPub Atom Entry XML を組み立て（`<title>` / `<updated>` / `<content type="text/x-markdown">` / `<app:draft>yes</app:draft>` / `<category>`）
8. Basic 認証で --force なしは POST、--force ありは既存 edit_url へ PUT
9. POST 成功時 published.jsonl に 1 行 JSON を追記、PUT 成功時は既存行を保持

使用例:

    python scripts/publish_hatena.py              # 最新の記事を下書き登録（POST）
    python scripts/publish_hatena.py 2026-05-13   # 指定日付の記事を下書き登録（POST）
    python scripts/publish_hatena.py --force      # 同日エントリを PUT で更新
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import sys
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


_ARTICLE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-")


def select_article(date: str | None) -> pathlib.Path:
    """対象記事を選ぶ. date 指定時は前方一致、未指定時はファイル名順で最新.

    ファイル名は `YYYY-MM-DD-HH-MM-SS-<slug>.md` 形式（write-hatena-diary 仕様）のため、
    辞書順ソートで時系列順になる。mtime ではなくファイル名でソートするのは、
    `touch` 等で mtime が書き換わっても選択結果が安定するため。

    日付プレフィックスを持たない補助ファイル（README.md 等）は候補から除外する。
    """
    if not ARTICLES_DIR.exists():
        raise SystemExit(f"記事ディレクトリが存在しません: {ARTICLES_DIR}")
    candidates = sorted(
        p for p in ARTICLES_DIR.glob("*.md") if _ARTICLE_NAME_RE.match(p.name)
    )
    if not candidates:
        raise SystemExit(
            f"対象記事がありません: {ARTICLES_DIR}/YYYY-MM-DD-HH-MM-SS-*.md"
        )
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise SystemExit(f"日付形式が不正です（YYYY-MM-DD で指定）: '{date}'")
        matched = [p for p in candidates if p.name.startswith(date)]
        if not matched:
            raise SystemExit(f"日付 {date} に対応する記事がありません: {ARTICLES_DIR}")
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
    `<app:draft>yes/no</app:draft>` で下書き/公開を切り替える。
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


def basic_auth_header(hatena_id: str, api_key: str) -> str:
    token = base64.b64encode(f"{hatena_id}:{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


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
    req = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": basic_auth_header(hatena_id, api_key),
            "Content-Type": "application/atom+xml; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
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

    payload = build_atom_entry(
        title=title,
        body=body,
        category=category,
        draft=True,
        published_iso=published_iso,
    )

    if args.force:
        assert existing is not None
        target_edit_url = existing["edit_url"]
        assert target_edit_url is not None
        print(f"🔄 PUT 中 (title: {title})", file=sys.stderr)
        status, response = put_entry(
            edit_url=target_edit_url,
            hatena_id=hatena_id,
            api_key=api_key,
            payload=payload,
        )
        op_label = "下書き更新成功"
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
        print("  published.jsonl は既存エントリを保持（--force による更新のため）")
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
