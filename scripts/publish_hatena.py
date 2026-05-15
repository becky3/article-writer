"""生成済みの日記記事を AtomPub で下書きとして投稿する.

仕様: .claude/skills/publish-hatena/SKILL.md

処理:

1. 対象記事を選択（引数: 日付 YYYY-MM-DD、未指定時は最新ファイル）
2. articles/hatena/published.txt で重複検知（同日付エントリの有無で判定）
3. フロントマター（title / date / category）を解析、本文を取得
4. リポジトリルートの .env から HATENA_ID / HATENA_BLOG_ID を取得
5. keyring から HATENA_API_KEY を取得（service="article-writer"）
6. AtomPub Atom Entry XML を組み立て（`<title>` / `<updated>` / `<content type="text/x-markdown">` / `<app:draft>yes</app:draft>` / `<category>`）
7. Basic 認証で POST
8. 成功時に published.txt にエントリを追記し、Entry ID と管理画面 URL を表示

使用例:

    python scripts/publish_hatena.py              # 最新の記事を下書き登録
    python scripts/publish_hatena.py 2026-05-13   # 指定日付の記事を下書き登録
    python scripts/publish_hatena.py --force      # 重複検知を無視して投稿
"""
from __future__ import annotations

import argparse
import base64
import pathlib
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import keyring

SERVICE = "article-writer"
KEY_API_KEY = "HATENA_API_KEY"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ARTICLES_DIR = REPO_ROOT / "articles" / "hatena"
PUBLISHED_TXT = ARTICLES_DIR / "published.txt"


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


def check_duplicate(diary_date: str) -> bool:
    """記事フロントマターの diary 日付が既に published.txt にあるか確認する.

    本ツールは 1 日 1 記事を前提とするため、同じ日付のエントリが既にあれば
    重複と判定する。
    """
    if not PUBLISHED_TXT.exists():
        return False
    for line in PUBLISHED_TXT.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(f"- ({diary_date})"):
            return True
    return False


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


def post_entry(
    *,
    hatena_id: str,
    blog_id: str,
    api_key: str,
    payload: bytes,
) -> tuple[int, str]:
    """AtomPub に POST する.

    戻り値の HTTP status はネットワーク失敗時 -1 を返す（HTTP ステータスと識別可能にするため）。
    呼び出し元は 200/201 以外を全て失敗として扱う。
    """
    url = f"https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/atom/entry"
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
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


def extract_entry_id(response_body: str) -> str | None:
    try:
        root = ET.fromstring(response_body)
    except ET.ParseError:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    elem = root.find("atom:id", ns)
    return elem.text if elem is not None else None


def extract_edit_url(response_body: str) -> str | None:
    """レスポンスから人間向けの編集 URL（rel="alternate"）を取り出す."""
    try:
        root = ET.fromstring(response_body)
    except ET.ParseError:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for link in root.findall("atom:link", ns):
        if link.get("rel") == "alternate":
            return link.get("href")
    return None


def append_published(diary_date: str, title: str) -> None:
    """published.txt に 1 行追記する.

    日付欄は記事フロントマターの `date:` をそのまま使う（日記対象日）。
    """
    line = f"- ({diary_date}) {title}\n"
    PUBLISHED_TXT.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISHED_TXT.open("a", encoding="utf-8") as f:
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
        help="published.txt の重複検知を無視して投稿する",
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

    already_published = check_duplicate(diary_date)
    if already_published and not args.force:
        msg = (
            f"⚠️ 同じ日付 ({diary_date}) のエントリが既に published.txt にあります\n"
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
    print(f"📤 POST 中 (title: {title})", file=sys.stderr)

    status, response = post_entry(
        hatena_id=hatena_id,
        blog_id=blog_id,
        api_key=api_key,
        payload=payload,
    )

    if status not in (200, 201):
        if status == -1:
            print(f"❌ ネットワークエラー: {response}", file=sys.stderr)
            print("  少し時間を置いてから再実行する", file=sys.stderr)
        else:
            print(f"❌ HTTP {status}", file=sys.stderr)
            print(response, file=sys.stderr)
        return 1

    entry_id = extract_entry_id(response)
    edit_url = extract_edit_url(response)
    print("✅ 下書き登録成功")
    print(f"  記事: {article_path.relative_to(REPO_ROOT)}")
    print(f"  Entry ID: {entry_id if entry_id else '(取得失敗・管理画面で確認)'}")
    if edit_url:
        print(f"  URL: {edit_url}")

    append_failed = False
    if not already_published:
        try:
            append_published(diary_date, title)
            print("  published.txt に追記済み")
        except OSError as e:
            append_failed = True
            line = f"- ({diary_date}) {title}"
            print(
                f"  ⚠️ published.txt 追記に失敗: {e}\n"
                f"  以下の行を {PUBLISHED_TXT.relative_to(REPO_ROOT)} に追記する:\n"
                f"    {line}",
                file=sys.stderr,
            )
    else:
        print("  published.txt は既存エントリを保持（--force による再投稿のため）")

    print(f"  管理画面: https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/edit")
    return 1 if append_failed else 0


if __name__ == "__main__":
    sys.exit(main())
