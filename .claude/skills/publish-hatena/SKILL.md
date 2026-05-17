---
name: publish-hatena
description: 生成済みの日記記事を、はてなブログ AtomPub で下書きとして投稿する
user-invocable: true
allowed-tools: Bash, Read
argument-hint: "[YYYY-MM-DD] [--force]"
---

## タスク

`articles/hatena/` 配下の生成済み日記記事を、はてなブログの AtomPub エンドポイントへ送信し下書き（`<app:draft>yes</app:draft>`）として登録する。投稿成功時に `articles/hatena/published.jsonl` へ記録を追記する。

公開（`<app:draft>no</app:draft>`）の自動投稿は本スキルの対象外。下書き登録後の公開判断と「公開」操作はオーナーがはてなブログの管理画面で行う。

仕様: `aidlc-docs/plan-work/issue-42.md`

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: `articles/hatena/` 配下のファイル名順で最新のファイルを対象とする
- **`YYYY-MM-DD`**: ファイル名がこの日付で始まる記事を対象とする。同日複数あれば最新を選択
- **`--force`**: `published.jsonl` から対象日付の `edit_url` を取得し、AtomPub PUT で既存エントリを上書き更新する。`published.jsonl` の該当行の `title` を最新タイトルに更新する（`edit_url` は既存値を保持、行追加はしない）
  - 対象日付のエントリが `published.jsonl` に未登録の場合はエラー停止（`--force` は更新専用のため、新規投稿には使えない）
  - 対象日付のエントリは登録されているが `edit_url` が `null` の場合もエラー停止。手動で `edit_url` を URL 文字列に書き換えてから再実行する
- 上記の組み合わせ可（例: `2026-05-13 --force`）

## 前提条件

以下が事前に整備されていること（オーナーによる初期設定）。未整備の場合はスクリプトがエラーで停止する。

| 項目 | 場所 | 内容 |
|---|---|---|
| `HATENA_ID` | リポジトリルートの `.env` | はてなのユーザー名（公開情報） |
| `HATENA_BLOG_ID` | リポジトリルートの `.env` | ブログのホスト名（`<subdomain>.hatenablog.com` 形式、公開情報） |
| `HATENA_API_KEY` | keyring（`service="article-writer"`） | AtomPub 用 API キー（秘匿情報。ダッシュボード → 設定 → 詳細設定 → AtomPub の「APIキー」） |
| 投稿先ブログの編集モード | はてなブログの基本設定 | **Markdown** に設定済み（運用前提。詳細は `.claude/skills/write-hatena-diary/quality-guidelines.md` Part 2「記法」を参照） |

`.env` は `.gitignore` 済み。`HATENA_API_KEY` の値はオーナー手元のみで管理する秘匿情報で、本スキルから値を出力・記録しない。keyring 登録の具体コマンドは <<## エラーハンドリング一覧@self>> を参照。

## 処理手順

### Phase 0: 環境セットアップ（worktree 対応）

`.env` はリポジトリルートに配置する必要があるが、git-worktree で作業中は worktree 側に `.env` が存在しない（`.gitignore` 対象のためチェックアウトされない）。

スクリプト実行前に以下を確認し、必要なら親リポからコピーする:

```bash
if [ ! -f .env ]; then
  # git worktree list --porcelain の "worktree <path>" 行を抽出（パスにスペースを含んでも安全）
  MAIN_REPO=$(git worktree list --porcelain | awk '/^worktree /{sub(/^worktree /,""); print; exit}')
  if [ -n "$MAIN_REPO" ] && [ -f "$MAIN_REPO/.env" ]; then
    cp "$MAIN_REPO/.env" .env
    echo "INFO: 親リポから .env をコピーしました: $MAIN_REPO/.env -> .env"
  fi
fi
```

実行される条件は **カレントに `.env` が無い** ことのみ。worktree 内では `.env` がチェックアウトされないため通常該当する。親リポで直接実行している場合は通常 `.env` が存在するため外側の `if` で弾かれて実質スキップされる。

カレントにも親リポにも `.env` がない場合は初期設定未整備のため、本セクション冒頭「前提条件」テーブルに従い `.env` を新規作成してから再実行する。

### Phase 1: 引数パース

1. `$ARGUMENTS` を空白で分割
2. `YYYY-MM-DD` 形式のトークンがあれば `DATE` に格納
3. `--force` があれば `FORCE=1`
4. それ以外のトークンが残ればエラー停止

### Phase 2: 投稿実行

`scripts/publish_hatena.py` を呼ぶ:

```bash
python scripts/publish_hatena.py [<DATE>] [--force]
```

スクリプトの責務:

1. 対象記事の選択（`DATE` 指定時はファイル名前方一致、未指定時は最新）
2. フロントマター（`title` / `date` / `category`）解析と本文取得
3. 本文先頭の `# <title>` 行剥がし（はてなブログはエントリ title を別管理するため重複を避ける）
4. **簡素記法ブロックを HTML に展開**: `scripts/convert_article_html.py` の `convert()` を呼び、`:::kuro-chan` / `:::nee-san` / `:::bluesky` を対応 HTML へ変換する（記法仕様は `.claude/skills/write-hatena-diary/balloon-html.md`）。変換エラー時はスクリプト全体を停止
5. `published.jsonl` から対象日付のエントリを検索し、登録状態（未登録 / 登録済みで `edit_url` が `null` / 登録済みで `edit_url` が URL 文字列）を判定する
6. `--force` 分岐の確定:
   - `--force` なし & 対象日付が登録済み → 重複警告で停止
   - `--force` あり & 未登録 → エラー停止（更新対象なし）
   - `--force` あり & 登録済み・`edit_url` が `null` → エラー停止（手動書き換えの案内）
   - `--force` あり & 登録済み・`edit_url` が URL 文字列 → PUT を実行
   - `--force` なし & 未登録 → POST を実行
7. `.env` から `HATENA_ID` / `HATENA_BLOG_ID` を取得
8. keyring から `HATENA_API_KEY` を取得
9. Atom Entry XML を組み立て（`<title>` / `<updated>`（フロントマター `date:` を JST 0 時として ISO 8601 化、はてなブログ管理画面で公開予定日として表示される） / `<content type="text/x-markdown">` / `<app:draft>yes</app:draft>` / `<category term="...">`）
10. Basic 認証でリクエスト送信
    - POST 時: `https://blog.hatena.ne.jp/<HATENA_ID>/<HATENA_BLOG_ID>/atom/entry`
    - PUT 時: 取得済みの `edit_url`
11. POST 成功時の `published.jsonl` 追記:
    - レスポンスの `<link rel="edit" href="..."/>` を抽出し `{"date": "<日付>", "title": "<title>", "edit_url": "<URL>"}` 形式で 1 行 JSON を追記する
    - `edit_url` 抽出に失敗した場合: WARNING を出して `"edit_url": null` で追記する（次回 `--force` 前に手動書き換えが必要、終了コード `0`）
    - 追記が I/O 失敗した場合: WARNING + 追記すべき 1 行を明示し終了コード `1`（投稿自体は成功している点を明示）
12. PUT 成功時は `published.jsonl` の該当行の `title` を最新タイトルに更新する（`edit_url` は既存値を保持、行追加はしない）
13. レスポンスの `<link rel="alternate" href="..."/>`（公開閲覧 URL）と `<atom:id>` を画面表示する

### Phase 3: 結果報告

スクリプトの出力をそのままユーザーに見せる。成功時の典型出力（POST）:

```text
📄 対象記事: articles/hatena/YYYY-MM-DD-diary.md
📤 POST 中 (title: ...)
✅ 下書き登録成功
  記事: articles/hatena/...
  Entry ID: tag:blog.hatena.ne.jp,...:entry-...
  URL: https://<blog>/entry/...
  published.jsonl に追記済み（edit_url 含む）
  管理画面: https://blog.hatena.ne.jp/<HATENA_ID>/<HATENA_BLOG_ID>/edit
```

成功時の典型出力（`--force` での PUT）:

```text
📄 対象記事: articles/hatena/YYYY-MM-DD-diary.md
🔄 PUT 中 (title: ...)
✅ 下書き更新成功
  記事: articles/hatena/...
  Entry ID: tag:blog.hatena.ne.jp,...:entry-...
  URL: https://<blog>/entry/...
  published.jsonl の title を最新タイトルに更新（edit_url は保持）
  管理画面: https://blog.hatena.ne.jp/<HATENA_ID>/<HATENA_BLOG_ID>/edit
```

エラー時はスクリプトの stderr 出力をそのまま見せ、再実行可否を判断する。

## エラーハンドリング一覧

| ケース | 対応 |
|---|---|
| `.env` が見つからない | スクリプトがエラー表示 + 停止。`.env` 作成例を案内 |
| `.env` に `HATENA_ID` または `HATENA_BLOG_ID` が未設定 | スクリプトがエラー表示 + 停止 |
| keyring に `HATENA_API_KEY` が未登録 | スクリプトがエラー表示 + 停止。本スキルは値を扱えないため、オーナーが以下のコマンドで対話入力で登録する（シェル履歴に値を残さないため `getpass` を使用）。`python -c "import keyring, getpass; keyring.set_password('article-writer', 'HATENA_API_KEY', getpass.getpass('API Key: '))"` |
| 対象記事ディレクトリが存在しない | スクリプトがエラー表示 + 停止 |
| 引数日付に対応する記事がない | スクリプトがエラー表示 + 停止 |
| 引数の日付形式が不正 | スクリプトがエラー表示 + 停止 |
| フロントマター（`title` / `date`）が未設定 | スクリプトがエラー表示 + 停止 |
| フロントマター `date:` が `YYYY-MM-DD` 形式でない | スクリプトがエラー表示 + 停止（`<updated>` 組み立て前に検証する） |
| 簡素記法ブロック（`:::kuro-chan` / `:::nee-san` / `:::bluesky`）の構文エラー（未閉鎖・必須キー欠落等） | スクリプトがエラー表示 + 停止。エラーメッセージは行番号付き |
| 同じ日付のエントリが既に `published.jsonl` に存在（重複検知、`--force` なし） | スクリプトが警告 + 停止。再投稿が妥当なら `--force` で再実行する |
| `--force` 指定だが対象日付のエントリが `published.jsonl` に未登録 | スクリプトがエラー停止。`--force` は更新専用のため、新規投稿時は `--force` を外して再実行する |
| `--force` 指定だが対象日付のエントリに `edit_url` が `null` | スクリプトがエラー停止 + 手動書き換えの手順を案内。はてなブログ管理画面から AtomPub edit URL を取得し、`published.jsonl` の該当行の `edit_url` を `null` から URL 文字列に書き換えてから再実行する |
| HTTP 401 / 403 | API キーまたは権限不足。keyring 登録値とブログオーナー権限を確認 |
| HTTP 404（PUT 時） | 指定 `edit_url` のエントリがはてな側に存在しない（手動削除済み等）。`published.jsonl` の該当行の `edit_url` を `null` に書き換え、通常 POST で再投稿する |
| HTTP 5xx / タイムアウト | リトライは実装しない。少し時間を置いてから再実行する |
| ネットワーク失敗（DNS / TCP / `URLError` / `TimeoutError`） | スクリプトは HTTP `-1` として扱い、`❌ ネットワークエラー: ...` を表示。少し時間を置いてから再実行する |
| POST 成功後の `published.jsonl` 追記が I/O 失敗 | スクリプトが Entry ID・公開閲覧 URL を表示しつつ WARNING + 追記すべき 1 行を明示。終了コード `1`。投稿自体は成功しているため、明示された 1 行を `published.jsonl` に追記して整合を回復する |
| POST 成功したがレスポンスから `edit_url` 抽出に失敗 | スクリプトが WARNING を出し、`"edit_url": null` で `published.jsonl` に追記する（終了コード `0`）。次回 `--force` 前に管理画面から AtomPub edit URL を確認して URL 文字列に書き換える必要がある |

## 注意事項

- 本スキルは **下書きの登録（POST）と更新（`--force` 指定時の PUT）** のみ対応する。公開（`<app:draft>no</app:draft>`）はサポートしない。下書きの公開判断はオーナーが管理画面で行う
- 削除（DELETE）はサポートしない。誤投稿時はオーナーが管理画面で削除する
- `--force` での PUT 対象は `published.jsonl` の `edit_url` が URL 文字列のエントリに限る。`edit_url` が `null` のエントリ（別環境投稿等で記録された場合）に `--force` を実行するとエラー停止するため、必要に応じて手動で `edit_url` を URL 文字列に書き換える
- リトライは実装しない。一時的失敗時は少し時間を置いてから再実行する
- `published.jsonl` に追記する日付は **記事フロントマターの `date:`（日記対象日）**。1 日 1 記事を前提に、同じ日付のエントリがあれば重複と判定する
- 本スキルは API キー値・認証情報を出力・記録しない（`~/.claude/rules/invariants.md` 「秘匿情報の出力禁止」遵守）

## 関連

- `scripts/publish_hatena.py`: 投稿スクリプト本体
- `scripts/convert_article_html.py`: 簡素記法 → HTML 変換（本スクリプトが投稿前に呼ぶ）
- `.claude/skills/write-hatena-diary/SKILL.md`: 日記記事の生成スキル
- `.claude/skills/write-hatena-diary/template-diary.md`: 記事テンプレート（フロントマター・固定 HTML・参照データ）
- `.claude/skills/write-hatena-diary/quality-guidelines.md`: 記法ポリシー含む品質ルール SSoT
- `.claude/skills/write-hatena-diary/balloon-html.md`: 簡素記法仕様（吹き出し・Bluesky）
- `articles/hatena/published.jsonl`: 公開済み記録（本スキルが追記する）
