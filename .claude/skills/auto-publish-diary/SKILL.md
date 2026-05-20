---
name: auto-publish-diary
description: 当日対象の日記記事を生成→はてな下書き登録→PR 作成→マージまで一括する無人実行向けワンショットスキル。Slack reminder からの定時実行を想定する。
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Skill
argument-hint: "(引数なし)"
---

## タスク

### allowed-tools 補足

- `Bash`: git / gh コマンド・`publish_hatena.py` の subprocess 起動・URL 抽出など全 Phase の中核
- `Read`: PR テンプレ・記事フロントマターの読み取り
- `Edit`: PR 本文の一時ファイル展開時のフォールバック
- `Write`: PR 本文一時ファイル `.tmp/auto-publish-diary/pr-body.md` の生成
- `Skill`: `/write-hatena-diary --auto-publish` の Skill 起動のみ（`/publish-hatena` は Bash で直接呼ぶ）

### 役割

`/write-hatena-diary --auto-publish` で当日対象の日記を生成し、`/publish-hatena` ではてなブログへ下書き登録した上で、git commit / PR 作成 / 即マージ / worktree クリーンアップまでを一気通貫で実行する。

呼び出し元（典型: ai-assistant の Slack コマンド → `claude -p`）が結果を機械的にパースできるよう、stdout の最終行に **JSON 1 行** を出力する。終了コードで成否を返す（0 = 成功 / 非 0 = 失敗）。

`AskUserQuestion` 等の対話発行は行わない。無人実行が前提。

## 起動方法

- **手動起動**: ユーザーが任意のタイミングで `/auto-publish-diary` を実行する（動作確認・本番投入前テスト用途）
- **自動起動**: ai-assistant の Slack コマンド経由で `claude -p /auto-publish-diary` を subprocess 起動する想定（呼び出し側の実装は別 Issue）

## 引数

引数なし。`$ARGUMENTS` に何らかのトークンが渡された場合は警告のみ表示して無視する（後方互換性確保のため停止しない）。

## 出力仕様

### stdout

各 Phase の進捗を自由形式で stdout に出力する。最終行に **JSON 1 行** を出力する。

成功時（全工程完了、worktree 削除済み）:

```json
{"status":"ok","article_path":"articles/hatena/YYYY-MM-DD-diary.md","draft_url":"https://<blog>/entry/...","pr_url":"https://github.com/becky3/article-writer/pull/N","merged":true,"worktree_removed":true,"worktree_path":null}
```

成功時（worktree 削除失敗、その他は完了）:

```json
{"status":"ok","article_path":"articles/hatena/YYYY-MM-DD-diary.md","draft_url":"https://<blog>/entry/...","pr_url":"https://github.com/becky3/article-writer/pull/N","merged":true,"worktree_removed":false,"worktree_path":"D:/GitHub/becky3/article-writer-wt-auto-YYYYMMDD"}
```

失敗時:

```json
{"status":"error","failed_phase":"<Phase 名>","error":"<エラー要約 1 行>","worktree_path":"<残置 worktree の絶対パス or null>","article_path":"<生成済みなら相対パス、なければ null>","draft_url":"<登録済みなら URL、なければ null>","pr_url":"<作成済みなら URL、なければ null>","merged":false}
```

JSON フィールドの説明（全モード共通スキーマ）:

| フィールド | 型 | 成功時 | 失敗時 |
|---|---|---|---|
| `status` | string | `"ok"` | `"error"` |
| `article_path` | string \| null | 生成記事の相対パス | 生成済みなら相対パス、なければ null |
| `draft_url` | string \| null | はてなブログの公開予定 URL（`scripts/publish_hatena.py` が返す `rel=alternate` URL。下書き登録後・公開時に有効化される） | 登録済みなら URL、なければ null |
| `pr_url` | string \| null | 作成された PR の URL | 作成済みなら URL、なければ null |
| `merged` | bool | true | false（マージまで到達しなかったため） |
| `worktree_removed` | bool | 削除済みなら true / 削除失敗時は false | false（残置） |
| `worktree_path` | string \| null | 削除済みなら null / 削除失敗時は残置パス | 残置 worktree の絶対パス（worktree 作成前に失敗した場合は null） |
| `failed_phase` | string | （省略） | 失敗 Phase 名（`environment` / `write` / `publish` / `git` / `cleanup`） |
| `error` | string | （省略） | エラー要約 1 行 |

### 終了コード

| 値 | 意味 |
|---|---|
| 0 | 全 Phase 成功（worktree 削除済み） |
| 1 | 失敗（JSON `status=error` を出力済み。worktree は残置） |

## 処理手順 (Phase 0〜5)

シェル設定: 各 Phase の Bash コマンド群は冒頭で `set -euo pipefail` を宣言する。`set -e` で失敗即停止、`set -u` で未定義変数を検出、`set -o pipefail` でパイプ途中の失敗を検出する。失敗判定は `|| true` を必要な箇所にだけ局所的に許可する。

各 Phase の冒頭で `[PHASE <名前>] 開始` を、完了時に `[PHASE <名前>] 完了` を stdout に出力する。失敗時は `[PHASE <名前>] 失敗: <理由>` を出力した上で、後続 Phase をスキップして最終 JSON を出力 + 終了コード 1 で終了する。

### Phase 0: 環境準備

1. 実行コンテキスト確認:
   - `PARENT_REPO=$(git rev-parse --show-toplevel)` を保存（後続 Phase で再利用）
   - 親リポジトリで実行されていることを以下で確認:

     ```bash
     GIT_DIR_REAL=$(realpath "$(git rev-parse --git-dir)")
     GIT_COMMON_DIR_REAL=$(realpath "$(git rev-parse --git-common-dir)")
     [ "$GIT_DIR_REAL" = "$GIT_COMMON_DIR_REAL" ] || { echo "[PHASE environment] 失敗: worktree 内からの起動は非対応"; exit 1; }
     ```

   - worktree 内から起動された場合は失敗扱い（`failed_phase=environment`、`error=worktree 内からの起動は非対応`、`worktree_path=null`）
2. 親リポ clean 確認 + main 最新化:
   - `git -C "$PARENT_REPO" status --porcelain` の結果が空でない場合は失敗扱い（`failed_phase=environment`、`error=親リポに未コミット変更があります`、`worktree_path=null`）。`claude -p` 経由で他作業の進行中ブランチを踏み潰すことを防ぐ
   - clean なら `git -C "$PARENT_REPO" switch main && git -C "$PARENT_REPO" pull --ff-only` で main を最新化する。失敗は `failed_phase=environment` で停止
3. ブランチ名・worktree パスを決定（`git rev-parse --show-toplevel` を 1 度だけ呼び、`PARENT_REPO` から派生させる）:

   ```bash
   REPO_NAME=$(basename "$PARENT_REPO")
   PARENT_DIR=$(dirname "$PARENT_REPO")
   DATE_SUFFIX=$(date '+%Y%m%d')
   BRANCH_NAME="auto/diary-$(date '+%Y-%m-%d')"
   WORKTREE_PATH="${PARENT_DIR}/${REPO_NAME}-wt-auto-${DATE_SUFFIX}"
   ```

   **命名規約例外**: `~/.claude/docs/specs/workflows/git-worktree.md` の規約 `<リポジトリ名>-wt-<Issue 番号>` は、auto-publish 経路では対応する Issue を持たないため、Issue 番号の代わりに `auto-YYYYMMDD` を識別子として用いる
4. 同名ブランチが既に存在する場合は失敗扱い（同日に二重実行）。worktree 作成前に事前検査:

   ```bash
   if git -C "$PARENT_REPO" rev-parse --verify "refs/heads/$BRANCH_NAME" >/dev/null 2>&1; then
     echo "[PHASE environment] 失敗: ブランチが既に存在: $BRANCH_NAME"; exit 1
   fi
   ```

   `failed_phase=environment`、`error=ブランチが既に存在: <BRANCH_NAME>`、`worktree_path=null`
5. `git -C "$PARENT_REPO" worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH" main` で worktree 作成。失敗時は `failed_phase=environment`
6. `cd "$WORKTREE_PATH"` で worktree に移動。以降の Bash は worktree を cwd として動作する
7. `.env` を worktree にコピー（`/publish-hatena` Phase 0 でも同等処理が走るが、本スキルで先回りしておくとエラーメッセージが整理される）:
   - 親リポに `.env` があれば `cp "$PARENT_REPO/.env" "$WORKTREE_PATH/.env"`
   - 親リポにもない場合は失敗扱い（`failed_phase=environment`、`error=.env が見つかりません`、`worktree_path=$WORKTREE_PATH`）
   - コピー後に `grep -qE "^HATENA_ID=" .env && grep -qE "^HATENA_BLOG_ID=" .env` で必須キーの存在を検証。欠落時は失敗扱い（`failed_phase=environment`、`error=.env に HATENA_ID または HATENA_BLOG_ID が未設定`）

### Phase 1: 記事生成

1. `Skill` ツールで `/write-hatena-diary --auto-publish` を起動する（日付引数なし = 既存 `auto-next` モードで対象日を自動推定）
2. `/write-hatena-diary` の構造化メッセージから生成記事パスを抽出する。書式: `📁 生成記事: <相対パス>` を期待し、Bash で `grep -oE '^📁 生成記事: articles/hatena/[0-9]{4}-[0-9]{2}-[0-9]{2}-diary\.md$' | sed 's/^📁 生成記事: //'` のように 1 行 1 ファイルとして抽出する
3. **単一日選定ルール**: 抽出結果が 0 件なら失敗扱い（`failed_phase=write`、`error=記事生成に失敗`）。複数行が抽出された場合（範囲との誤併用時の保険）は、実行日（`date '+%Y-%m-%d'`）と一致するファイル名の行を優先採用し、一致 0 件なら最も新しい日付の 1 件を採用する
4. `ARTICLE_PATH` 変数に格納（最終 JSON 用）

### Phase 2: Hatena 下書き登録

`/publish-hatena` の Skill ツール経由起動では subprocess の stderr / exit code を直接取得する手段がないため、本 Phase は `python scripts/publish_hatena.py` を Bash で直接起動する。

Phase 1 で確定した `ARTICLE_PATH` と異なる記事を誤って投稿しないよう、ファイル名から日付を抽出して `publish_hatena.py` に引数として明示的に渡す（引数なし起動だと `articles/hatena/` 内の最新ファイルが選ばれるため、別日の手動生成ファイルが存在すると誤投稿リスクがある）:

1. 投稿実行（ログ出力先ディレクトリは tee 前に必ず作成する）:

   ```bash
   mkdir -p .tmp/auto-publish-diary
   PUBLISH_DATE=$(basename "$ARTICLE_PATH" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
   if [ -z "$PUBLISH_DATE" ]; then
     echo "[PHASE publish] 失敗: ARTICLE_PATH から日付を抽出できず: ${ARTICLE_PATH}"; exit 1
   fi
   python scripts/publish_hatena.py "$PUBLISH_DATE" 2> .tmp/auto-publish-diary/publish-stderr.log | tee .tmp/auto-publish-diary/publish-stdout.log
   PUBLISH_EXIT=${PIPESTATUS[0]}
   ```

2. `PUBLISH_EXIT` が 0 でない場合は失敗扱い:

   ```bash
   STDERR_TAIL=$(tail -1 .tmp/auto-publish-diary/publish-stderr.log | tr -d '\r\n' || true)
   if [ -z "$STDERR_TAIL" ]; then
     ERROR_MSG="publish_hatena.py が exit code ${PUBLISH_EXIT} で異常終了（stderr 空）"
   else
     ERROR_MSG="publish_hatena.py exit ${PUBLISH_EXIT}: ${STDERR_TAIL}"
   fi
   echo "[PHASE publish] 失敗: ${ERROR_MSG}"; exit 1
   ```

   `failed_phase=publish`、`error=${ERROR_MSG}`
3. 下書き登録後の公開予定 URL を抽出する。`scripts/publish_hatena.py` の成功時出力には、インデント 2 スペース + `URL:` プレフィックス + URL の行と、同様に `管理画面:` プレフィックス付きの行が並列に出力される:

   ```bash
   DRAFT_URL=$(grep -E '^  URL: ' .tmp/auto-publish-diary/publish-stdout.log | head -1 | sed 's/^  URL: //')
   ```

   `DRAFT_URL` が空の場合は失敗扱い（`failed_phase=publish`、`error=URL 抽出に失敗（Hatena 投稿は成功している可能性あり。published.jsonl を確認）`）

   **「下書き URL」の概念注記**:
   `scripts/publish_hatena.py` が返す `URL:` 行は AtomPub レスポンスの `<link rel="alternate" href="..."/>` を抽出したもので、**公開時に有効化される URL**（公開予定 URL）。
   下書き状態のプレビュー URL ではない。
   本スキルの JSON フィールド名は `draft_url` のままだが、意味は「下書き登録された記事の公開予定 URL」となる。

### Phase 3: git 操作（commit + push + PR + merge）

本 Phase の冒頭で **`ARTICLE_DATE`**・**`ARTICLE_TITLE`** を記事フロントマターから抽出して以降の処理で一貫して使う。`$(date ...)` のシェル実行時刻は使わない（深夜実行・auto-next モードで過去日対象になる場合に乖離するため）:

```bash
ARTICLE_DATE=$(awk '/^date:/{gsub(/["'\'']/, "", $2); print $2; exit}' "$ARTICLE_PATH")
ARTICLE_TITLE=$(awk '/^title:/{sub(/^title:[ ]*/, ""); gsub(/^["'\'']|["'\'']$/, ""); print; exit}' "$ARTICLE_PATH")

if [ -z "$ARTICLE_DATE" ] || [ -z "$ARTICLE_TITLE" ]; then
  echo "[PHASE git] 失敗: フロントマター読取失敗（date または title が空）"; exit 1
fi
if ! echo "$ARTICLE_DATE" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
  echo "[PHASE git] 失敗: フロントマター読取失敗（date 形式不正: ${ARTICLE_DATE}）"; exit 1
fi
```

`ARTICLE_DATE` の空チェック・`YYYY-MM-DD` 形式検証・`ARTICLE_TITLE` の空チェックは明示的に行う（`set -euo pipefail` 下でも awk の戻り値は 0 のため、空・形式不正のチェックを書かないとスルーされる）。失敗時は `failed_phase=git`、`error=フロントマター読取失敗（理由）`。

1. ステージング（記事 markdown と `published.jsonl` の追記をまとめてステージング）:

   ```bash
   git add articles/hatena/
   ```

2. コミット:

   ```bash
   git commit -m "diary: ${ARTICLE_DATE} の日記を追加"
   ```

   コミット失敗（変更が無い等）は失敗扱い（`failed_phase=git`、`error=<git commit の stderr 要約>`）

3. push:

   ```bash
   git push -u origin "$BRANCH_NAME"
   ```

4. PR 本文の組み立て（`gh pr create --body-file` 経由で特殊文字エスケープ・改行保持を両立する）。プレースホルダ置換は `scripts/replace_pr_placeholders.py`（`str.replace` ベース）を使い、`&` / `\` / `|` / 改行などの特殊文字を全てリテラル扱いにする（sed/awk は置換側の `&` `\` を特殊文字として解釈するため使わない）:

   ```bash
   mkdir -p .tmp/auto-publish-diary
   PR_BODY_FILE=".tmp/auto-publish-diary/pr-body.md"
   cp .github/PULL_REQUEST_TEMPLATE/auto-diary.md "$PR_BODY_FILE"
   python scripts/replace_pr_placeholders.py "$PR_BODY_FILE" \
     TITLE "$ARTICLE_TITLE" \
     DATE "$ARTICLE_DATE" \
     DRAFT_URL "$DRAFT_URL" \
     ARTICLE_PATH "$ARTICLE_PATH"
   ```

   Python 側で `str.replace` を使うため、タイトルや URL に `&` `\` `|` `$` 等の特殊文字が含まれていてもリテラル置換される

5. PR 作成（`--body-file` で本文を渡す）。`gh pr create` の stdout に追加行が混じるバージョン差異への耐性として `tail -1` で最終行のみ採用する:

   ```bash
   PR_URL=$(gh pr create \
     --base main \
     --head "$BRANCH_NAME" \
     --title "diary: ${ARTICLE_DATE} の日記を追加" \
     --body-file "$PR_BODY_FILE" | tail -1)
   PR_NUMBER=$(echo "$PR_URL" | grep -oE '/pull/[0-9]+$' | grep -oE '[0-9]+$')
   if [ -z "$PR_NUMBER" ]; then
     echo "[PHASE git] 失敗: gh pr create 出力から PR 番号を抽出できず: ${PR_URL}"; exit 1
   fi
   ```

   `gh pr create` 失敗時は `failed_phase=git`、`error=<gh pr create の stderr>`

6. 即マージ（CI 待たず）。PR 番号で `gh pr merge` を呼ぶ:

   ```bash
   gh pr merge "$PR_NUMBER" --squash --admin --delete-branch
   ```

   `--admin` で必須レビュー等のブランチ保護をバイパスする。`--delete-branch` でマージ後にリモートブランチも削除する。失敗時は失敗扱い（`failed_phase=git`、`error=<gh pr merge の stderr 要約>`）

   **前提**: `gh auth status` で確認できる認証ユーザーが対象リポの Admin 権限を持つこと（becky3 個人リポの owner なら満たす）。組織リポへ移行する場合は本前提を再確認すること

### Phase 4: worktree クリーンアップ

成功パスのみ実行する。Phase 0〜3 のいずれかで失敗した場合は本 Phase をスキップして worktree を残置する。

Phase 0 ステップ 1 で保存した `PARENT_REPO` をそのまま使うため、本 Phase 内で親リポパスを再計算しない。

1. 親リポジトリへ戻る:

   ```bash
   cd "$PARENT_REPO"
   ```

2. worktree 削除:

   ```bash
   git worktree remove --force "$WORKTREE_PATH" || WORKTREE_REMOVE_FAILED=1
   ```

   削除失敗（Windows ファイルロック等）の場合は `WORKTREE_REMOVE_FAILED=1` を立てるが、Phase 3 までは成功しているため `status=ok` で終了する。最終 JSON の `worktree_removed` は `false` とし、`worktree_path` に残置パスを含める。終了コードは 0

3. ローカルブランチ削除（マージ済みのみ削除する `-d` を使う。`-D` 強制削除は禁止）:

   ```bash
   git branch -d "$BRANCH_NAME" 2>/dev/null || true
   ```

   削除失敗は無視する（リモートが `--delete-branch` で消されている場合、ローカル追跡ブランチは自動的に消えるためエラーが出ても無害。未マージ状態なら `-d` は保護されるが、Phase 3-6 でマージ成功している前提のため通常は削除可）

4. 親リポ main の最新化（squash マージ済みコミットをローカルへ取り込む）:

   ```bash
   git pull --ff-only origin main 2>/dev/null || true
   ```

   PR が `gh pr merge --squash` でリモート main にマージ済みなので、本ステップで `--ff-only` で同期する。
   失敗（ネットワーク断・unexpected non-fast-forward 等）は無視し `status=ok` を保つ
   （次回 `/auto-publish-diary` 実行時の Phase 0 で再度同期される）。
   ユーザーが手動で別作業を始めるときに古い main から始める事故を防ぐのが目的

### Phase 5: 最終出力

成功時（worktree 削除済み）:

```text
[PHASE cleanup] 完了
✅ /auto-publish-diary 全工程成功
{"status":"ok","article_path":"...","draft_url":"...","pr_url":"...","merged":true,"worktree_removed":true,"worktree_path":null}
```

成功時（worktree 削除失敗、その他は完了）:

```text
[PHASE cleanup] 完了（worktree 残置: <パス>）
✅ /auto-publish-diary 全工程成功（worktree 削除のみ失敗）
{"status":"ok","article_path":"...","draft_url":"...","pr_url":"...","merged":true,"worktree_removed":false,"worktree_path":"..."}
```

失敗時:

```text
[PHASE <失敗 Phase>] 失敗: <理由>
❌ /auto-publish-diary 失敗（worktree 残置: <パス>）
{"status":"error","failed_phase":"...","error":"...","worktree_path":"...","article_path":"...","draft_url":null,"pr_url":null,"merged":false}
```

終了コード:

- 成功（worktree 削除済み）: 0
- 成功（worktree 削除失敗、その他は完了）: 0（`worktree_removed=false`）
- 失敗: 1

## エラーハンドリング一覧

| 状況 | failed_phase | 後続 Phase |
|---|---|---|
| worktree 内からの起動 | environment | スキップ。worktree 作成しないため `worktree_path=null` |
| 親リポに未コミット変更あり | environment | スキップ。`worktree_path=null` |
| `git switch main` / `git pull --ff-only` 失敗 | environment | スキップ。`worktree_path=null` |
| 同名ブランチ既存（同日二重実行） | environment | スキップ。`worktree_path=null` |
| `git worktree add` 失敗 | environment | スキップ。`worktree_path=null`（作成失敗のため） |
| `.env` が親リポにもない / 必須キー欠落 | environment | スキップ。`worktree_path=$WORKTREE_PATH`（worktree は作成済み） |
| `/write-hatena-diary` 失敗・生成記事 0 件 | write | publish 以降スキップ、worktree 残置 |
| `python scripts/publish_hatena.py` 失敗（HTTP 4xx/5xx、keyring 未登録等） | publish | git 以降スキップ、worktree + 記事 md は残置（再投稿可能） |
| URL 抽出失敗（publish 成功したが `URL:` 行が見つからない） | publish | git 以降スキップ。Hatena 側は投稿成功 + `published.jsonl` 追記済みの可能性が高いため、再実行時は `--force` での PUT 更新が必要 |
| 記事フロントマター読取失敗（`ARTICLE_DATE` / `ARTICLE_TITLE` が空 / 形式不正） | git | 後続スキップ、worktree 残置 |
| `git commit` 失敗（変更なし等） | git | merge スキップ、worktree 残置（既に Hatena 投稿済みのため要手動対応） |
| `git push` 失敗（remote 接続エラー等） | git | PR 作成スキップ |
| `gh pr create` 失敗 | git | merge スキップ |
| `gh pr merge` 失敗 | git | cleanup スキップ |
| `git worktree remove` 失敗（Windows ロック等） | (なし) | warning のみ。`status=ok` + `worktree_removed=false` で終了 |

## リカバリフロー

失敗 Phase ごとの典型的な手動リカバリ手順を以下に示す。Slack 通知側（ai-assistant）が運用者に手順を提示する想定。

| failed_phase | 状態 | 推奨リカバリ |
|---|---|---|
| `environment`（worktree 未作成） | 何も変更されていない | 失敗理由を解消（親リポを clean に / 同名ブランチを削除等）してから再実行 |
| `environment`（`.env` 不整合） | worktree のみ残置 | 親リポの `.env` を整備 → `git worktree remove --force <worktree_path>` で worktree 撤去 → 再実行 |
| `write` | worktree 残置 | ジャーナルの不足が原因なら素材を追加してから再実行。原因不明なら worktree 内で `/write-hatena-diary --auto-publish` を手動デバッグ |
| `publish` | 記事 md 生成済み、Hatena 未投稿 | worktree 内で `python scripts/publish_hatena.py` を手動再実行（HTTP エラー等は時間を置く） |
| `git`（commit 失敗より前） | 記事 md + Hatena 下書き登録済み、commit/PR なし | worktree 内で `git add articles/hatena/ && git commit -m "diary: <date> の日記を追加"` → push → PR → merge を手動実施 |
| `git`（commit 後に push/PR/merge 失敗） | commit 済み、リモート未反映 | `git push origin <branch>` を手動 → `gh pr create` 手動 → `gh pr merge` 手動 |
| `cleanup`（worktree 削除のみ失敗） | 全工程完了、worktree のみ残置 | `git -C <親リポ> worktree remove --force <worktree_path>` を手動。`status=ok` のため Slack 通知は成功扱い |

**published.jsonl の重複検知**: `publish-hatena` は成功時 `published.jsonl` に追記済みのため、同日に再実行すると重複エラーになる。再投稿が必要なら `python scripts/publish_hatena.py <date> --force` で既存エントリを PUT 更新する。

## 注意事項

- 本スキルは **無人実行** が前提。`AskUserQuestion` を発行しない。`claude -p` 非対話モードでは AskUserQuestion はエラー扱いされるため、スキル内で発行しないこと
- レビューでの修正適用は `/review-hatena-diary --auto-publish` 内の書き手自己判断に従う。設計判断・トレードオフを伴う指摘は無人実行のため棄却される
- PR は `gh pr merge --admin --squash` で即マージするため、ブランチ保護ルールがあっても通る。CI 実行は main へのマージ後（post-merge）に発生する想定
- **`gh pr merge --admin` 前提**: `gh auth status` で確認できる認証ユーザーが対象リポの Admin 権限を持つこと。becky3 個人リポではオーナー権限で満たすが、組織リポへ移行する場合は権限要件を再確認すること
- 同日二重実行は Phase 0 でブランチ名重複エラーになる。重複時は failed_phase=environment で終了するため、Slack 側で「本日は既に投稿済み」と通知できる
- 失敗時に Hatena に下書きだけ登録されたまま git に反映されないケース（`failed_phase=git`）は手動対応が必要。`published.jsonl` の追記までは publish-hatena が完了させているため、再実行時は `--force` での PUT 更新が必要
- **PR テンプレ配置の副作用**: `.github/PULL_REQUEST_TEMPLATE/auto-diary.md` は本スキル専用テンプレ。
  GitHub Web UI から手動 PR を作成すると本テンプレが選択肢に表示される副作用がある。
  本スキルは `gh pr create --body-file` 経由で本ファイルを読むため、CLI からは副作用なし。
  汎用 PR テンプレ整備は別 Issue で扱う

## 関連

- `.claude/skills/write-hatena-diary/SKILL.md`: 記事生成スキル本体（`--auto-publish` 経由で呼ぶ）
- `.claude/skills/review-hatena-diary/SKILL.md`: レビュースキル（`--auto-publish` 経由で呼ばれ書き手自己判断）
- `.claude/skills/publish-hatena/SKILL.md`: はてな AtomPub 投稿スキル
- `.github/PULL_REQUEST_TEMPLATE/auto-diary.md`: 自動投稿 PR の本文テンプレ
- `scripts/publish_hatena.py`: AtomPub 投稿スクリプト本体
- `scripts/replace_pr_placeholders.py`: PR テンプレのプレースホルダ置換補助スクリプト
