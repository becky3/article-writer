---
name: publish-hatena
description: 生成済みの日記記事を、はてなブログ AtomPub で下書きとして投稿する
user-invocable: true
allowed-tools: Bash, Read
argument-hint: "[YYYY-MM-DD] [--force]"
---

## タスク

`articles/hatena/` 配下の生成済み日記記事を、はてなブログの AtomPub エンドポイントへ送信し下書き（`<app:draft>yes</app:draft>`）として登録する。投稿成功時に `articles/hatena/published.txt` へ記録を追記する。

公開（`<app:draft>no</app:draft>`）の自動投稿は本スキルの対象外。下書き登録後の公開判断と「公開」操作はオーナーがはてなブログの管理画面で行う。

仕様: `aidlc-docs/plan-work/issue-42.md`

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: `articles/hatena/` 配下のファイル名順で最新のファイルを対象とする
- **`YYYY-MM-DD`**: ファイル名がこの日付で始まる記事を対象とする。同日複数あれば最新を選択
- **`--force`**: `published.txt` の重複検知を無視して再投稿する。`published.txt` には**追記しない**（既存行を保持）
- 上記の組み合わせ可（例: `2026-05-13 --force`）

## 前提条件

以下が事前に整備されていること（オーナーによる初期設定）。未整備の場合はスクリプトがエラーで停止する。

| 項目 | 場所 | 内容 |
|---|---|---|
| `HATENA_ID` | リポジトリルートの `.env` | はてなのユーザー名（公開情報） |
| `HATENA_BLOG_ID` | リポジトリルートの `.env` | ブログのホスト名（`<subdomain>.hatenablog.com` 形式、公開情報） |
| `HATENA_API_KEY` | keyring（`service="article-writer"`） | AtomPub 用 API キー（秘匿情報。ダッシュボード → 設定 → 詳細設定 → AtomPub の「APIキー」） |
| 投稿先ブログの編集モード | はてなブログの基本設定 | **Markdown** に設定済み（運用前提。詳細は `.claude/skills/write-hatena-diary/template-diary.md` の「記法ポリシー」を参照） |

`.env` は `.gitignore` 済み。`HATENA_API_KEY` の値はオーナー手元のみで管理する秘匿情報で、本スキルから値を出力・記録しない。keyring 登録の具体コマンドは <<## エラーハンドリング一覧@self>> を参照。

## 処理手順

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
4. `published.txt` の重複検知（フロントマターの `date:` と同じ日付のエントリが既にあるか）
5. `.env` から `HATENA_ID` / `HATENA_BLOG_ID` を取得
6. keyring から `HATENA_API_KEY` を取得
7. Atom Entry XML を組み立て（`<title>` / `<updated>`（フロントマター `date:` を JST 0 時として ISO 8601 化、はてなブログ管理画面で公開予定日として表示される） / `<content type="text/x-markdown">` / `<app:draft>yes</app:draft>` / `<category term="...">`）
8. Basic 認証で POST
9. 成功時に `published.txt` へ追記（`- (diary_date) title` 形式）し、Entry ID と編集 URL を表示。追記が I/O 失敗した場合は WARNING を出し、追記すべき 1 行を明示して終了コード `1` で返す（投稿自体は成功している点を明示）

### Phase 3: 結果報告

スクリプトの出力をそのままユーザーに見せる。成功時の典型出力:

```text
📄 対象記事: articles/hatena/YYYY-MM-DD-HHMMSS-<slug>.md
📤 POST 中 (title: ...)
✅ 下書き登録成功
  記事: articles/hatena/...
  Entry ID: tag:blog.hatena.ne.jp,...:entry-...
  URL: https://<blog>/entry/...
  published.txt に追記済み
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
| 同じ日付のエントリが既に `published.txt` に存在（重複検知） | スクリプトが警告 + 停止。再投稿が妥当なら `--force` で再実行する |
| HTTP 401 / 403 | API キーまたは権限不足。keyring 登録値とブログオーナー権限を確認 |
| HTTP 5xx / タイムアウト | リトライは実装しない。少し時間を置いてから再実行する |
| ネットワーク失敗（DNS / TCP / `URLError` / `TimeoutError`） | スクリプトは HTTP `-1` として扱い、`❌ ネットワークエラー: ...` を表示。少し時間を置いてから再実行する |
| POST 成功後の `published.txt` 追記が I/O 失敗 | スクリプトが Entry ID・編集 URL を表示しつつ WARNING + 追記すべき 1 行を明示。終了コード `1`。投稿自体は成功しているため、明示された 1 行を `published.txt` に追記して整合を回復する |

## 注意事項

- 本スキルは **下書き登録のみ**。公開（`<app:draft>no</app:draft>`）はサポートしない。下書き登録後の公開判断はオーナーが管理画面で行う
- 投稿後の編集（PUT）・削除（DELETE）はサポートしない。誤投稿時はオーナーが管理画面で削除する
- リトライは実装しない。一時的失敗時は少し時間を置いてから再実行する
- `published.txt` に追記する日付は **記事フロントマターの `date:`（日記対象日）**。1 日 1 記事を前提に、同じ日付のエントリがあれば重複と判定する
- 本スキルは API キー値・認証情報を出力・記録しない（`~/.claude/rules/invariants.md` 「秘匿情報の出力禁止」遵守）

## 関連

- `scripts/publish_hatena.py`: 投稿スクリプト本体
- `.claude/skills/write-hatena-diary/SKILL.md`: 日記記事の生成スキル
- `.claude/skills/write-hatena-diary/template-diary.md`: 記事テンプレート（フロントマター仕様・記法ポリシー）
- `articles/hatena/published.txt`: 公開済み記録（本スキルが追記する）
