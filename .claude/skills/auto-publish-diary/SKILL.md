---
name: auto-publish-diary
description: 当日対象の日記記事を生成→はてな下書き登録→PR 作成→マージまで一括する無人実行向けワンショットスキル。Slack reminder からの定時実行を想定する。
user-invocable: true
allowed-tools: Bash, Read, Skill
argument-hint: "(引数なし)"
---

## タスク

### 役割

当日対象の日記を生成し、はてなブログへ下書き登録した上で、git commit / PR 作成 / 即マージ / worktree クリーンアップまでを一気通貫で無人実行する。

決定論的な処理（環境準備・投稿・git・PR・マージ・cleanup・result.json 書き込み）は `scripts/auto_publish_diary.py` に集約されている。本スキルの責務は、その 2 エントリ（`setup` / `finalize`）の間に挟まる **記事生成（`/write-hatena-diary`、LLM ステップ）** をオーケストレーションすることだけ。

呼び出し元（典型: ai-assistant の Slack コマンド → `claude -p`）が結果を機械的にパースできるよう、`scripts/auto_publish_diary.py` が **レスポンスファイル** `$PARENT_REPO/.tmp/auto-publish-diary/result.json` に JSON を書き出す。

終了コードで成否を返す（0 = 成功 / 非 0 = 失敗）。

`AskUserQuestion` 等の対話発行は行わない。無人実行が前提。

### allowed-tools 補足

- `Bash`: `scripts/auto_publish_diary.py setup` / `finalize` の起動・生成記事パスの抽出
- `Read`: 生成記事の確認（必要時）
- `Skill`: `/write-hatena-diary --auto-publish` の起動（唯一の LLM ステップ）

## 起動方法

- **手動起動**: ユーザーが任意のタイミングで `/auto-publish-diary` を実行する（動作確認・本番投入前テスト用途）
- **自動起動**: ai-assistant の Slack コマンド経由で `claude -p /auto-publish-diary` を subprocess 起動する

## 引数

引数なし。`$ARGUMENTS` に何らかのトークンが渡された場合は警告のみ表示して無視する（後方互換性確保のため停止しない）。

## 出力仕様

### レスポンスファイル

呼び出し元への結果伝達は `scripts/auto_publish_diary.py` が書き出す **レスポンスファイル** `$PARENT_REPO/.tmp/auto-publish-diary/result.json` で行う。配置先は **親リポ固定**（worktree は cleanup で削除されるため）。`setup` 冒頭で前回残骸を削除し、成功時・失敗時の両方で必ず書き込む。

dict 生成の SSoT は `scripts/write_auto_publish_result.py` の `build_result()`。
result.json のスキーマ・各キーの意味・正規化ルール・`status` による分岐は同関数の docstring を参照する。
実例の JSON サンプルは `tests/test_write_auto_publish_result.py` の各テストケース（ok/削除済み・ok/削除失敗・error 等）を参照する。

`status` は `"ok"`（全 Phase 成功。`worktree_removed=false` の中間状態を含む）または `"error"`（任意 Phase で停止）の 2 値。スキーマのキー一覧（型と status 別出現条件のみ。各キーの意味・正規化ルールの SSoT は `build_result()` docstring）:

| フィールド | 型 | status="ok" | status="error" |
|---|---|---|---|
| `status` | string | 必須 | 必須 |
| `article_path` | string \| null | 必須 | 必須 |
| `edit_url` | string \| null | 必須 | 必須 |
| `public_url` | string \| null | 必須 | 必須 |
| `pr_url` | string \| null | 必須 | 必須 |
| `merged` | bool | 必須 | 必須 |
| `worktree_removed` | bool | 必須 | 必須 |
| `worktree_path` | string \| null | 必須 | 必須 |
| `worktree_remove_error` | string \| null | 必須 | 必須 |
| `failed_phase` | string | キー省略 | 必須 |
| `error` | string | キー省略 | 必須 |

### 終了コード

| 値 | 意味 |
|---|---|
| 0 | 全 Phase 成功（worktree 削除の成否によらず）。result.json は `status=ok` |
| 1 | 失敗（result.json に `status=error` を書き込み済み。worktree は残置） |

## 処理手順

`scripts/auto_publish_diary.py` の `setup` / `finalize` を起動し、その間に LLM ステップ（記事生成）を挟む。各 Python コマンドが result.json への書き込みと終了コードを自前で行うため、本スキルは終了コードを見て分岐するだけでよい。

### ステップ 1: setup（Phase 0）

親リポジトリの直下で **1 回だけ** 実行し、出力をファイルに保存してから終了コードを判定する（`setup` を 2 回起動するとブランチ名重複で必ず失敗するため、二重起動は厳禁）:

```bash
mkdir -p .tmp/auto-publish-diary
SETUP_LOG=.tmp/auto-publish-diary/setup-stdout.log
python scripts/auto_publish_diary.py setup > "$SETUP_LOG"
SETUP_EXIT=$?
if [ "$SETUP_EXIT" -ne 0 ]; then
  # result.json は setup が書き込み済み。本スキルもここで終了する
  exit 1
fi
WORKTREE=$(grep '^WORKTREE: ' "$SETUP_LOG" | sed 's/^WORKTREE: //')
```

`setup` の責務:

- 親リポ検証・clean 確認・main 最新化・worktree 作成・`.env` コピーを行う
- 成功時は stdout に `WORKTREE: <絶対パス>` と `BRANCH: <ブランチ名>` を出力する
- 失敗時は result.json（`status=error`、`failed_phase=environment`）を書き込み終了コード 1 で終了する

### ステップ 2: 記事生成（Phase 1・LLM）

`Skill` ツールで `/write-hatena-diary --auto-publish` を起動する（日付引数なし = `auto-next` モードで対象日を自動推定）。worktree 内で生成させるため、起動前に `cd "$WORKTREE"` する。

生成記事パスは構造化メッセージ `📁 生成記事: <相対パス>` から抽出する:

```bash
grep -oE '^📁 生成記事: articles/hatena/[0-9]{4}-[0-9]{2}-[0-9]{2}-diary\.md$' | sed 's/^📁 生成記事: //'
```

抽出できた相対パスを `ARTICLE_PATH` とする。生成に失敗して抽出が 0 件でも停止せず、空のまま次ステップへ渡す（`finalize` が `failed_phase=write` で記録する）。複数行抽出時は実行日（`date '+%Y-%m-%d'`）一致を優先、なければ最新日付の 1 件を採る。

### ステップ 3: finalize（Phase 2〜5）

worktree 内で実行する:

```bash
cd "$WORKTREE"
python scripts/auto_publish_diary.py finalize --article-path "$ARTICLE_PATH"
```

- Phase 2: `publish_hatena.py` を subprocess 起動して下書き登録 → `published.jsonl` から `edit_url` を読み、編集ページ URL・公開 URL を組み立てる
- Phase 3: git add / commit / push / `gh pr create` / `gh pr merge --squash --admin`（merge が exit 非 0 のときは `gh pr view --json state` で `MERGED` を確認できれば継続。Why は「注意事項」参照）
- Phase 4: 親リポへ戻り worktree 削除・ローカルブランチ削除・main 同期（削除失敗でも `status=ok`）
- Phase 5: `status=ok` の result.json を書き込む
- いずれかの Phase で失敗したら、`failed_phase` 付きの result.json を書き込み終了コード 1 で終了する

`finalize` は `git rev-parse` で parent_repo / worktree / branch を導出するため、本スキルから渡すのは `--article-path` のみ。

## エラーハンドリング一覧

result.json への書き込みと終了コードは `scripts/auto_publish_diary.py` が自前で行う。本スキルは終了コードを見て後続をスキップするだけ。

| 状況 | failed_phase | 後続 |
|---|---|---|
| worktree 内からの起動 / 親リポに未コミット変更 / `git switch main`・`pull` 失敗 / 同名ブランチ既存 / `git worktree add` 失敗 / `.env` 不整合 | environment | 以降スキップ |
| `/write-hatena-diary` 失敗・生成記事 0 件（`finalize` に空パスが渡る） | write | publish 以降スキップ、worktree 残置 |
| `publish_hatena.py` 失敗（HTTP 4xx/5xx・keyring 未登録等）/ 編集 URL 組み立て失敗 | publish | git 以降スキップ、worktree + 記事 md は残置（再投稿可能） |
| フロントマター読取失敗 / `git commit`・`push` 失敗 / `gh pr create` 失敗 / `gh pr merge` 失敗かつリモート state ≠ `MERGED` | git | 後続スキップ、worktree 残置 |
| `gh pr merge` exit 非 0 だがリモート state = `MERGED` | (なし) | warning のみ。Phase 4 へ継続（#219） |
| `git worktree remove` 失敗（Windows ロック等） | (なし) | warning のみ。`status=ok` + `worktree_removed=false` + `worktree_remove_error` に stderr 要約を格納して終了 |
| 外部コマンドのタイムアウト（120 秒超過） | 該当 Phase | error メッセージに「タイムアウト（120 秒）」を含めて識別可能にする |

## リカバリフロー

失敗状態の確認は `cat $PARENT_REPO/.tmp/auto-publish-diary/result.json` で行う（`failed_phase`・`error`・残置 worktree パス・部分到達した URL 等が確認できる）。Slack 通知側（ai-assistant）が運用者に手順を提示する想定。

| failed_phase | 状態 | 推奨リカバリ |
|---|---|---|
| `environment`（worktree 未作成） | 何も変更されていない | 失敗理由を解消（親リポを clean に / 同名ブランチを削除等）してから再実行 |
| `environment`（`.env` 不整合） | worktree のみ残置 | 親リポの `.env` を整備 → `git worktree remove --force <worktree_path>` で撤去 → 再実行 |
| `write` | worktree 残置 | ジャーナル素材を補ってから再実行。原因不明なら worktree 内で `/write-hatena-diary --auto-publish` を手動デバッグ |
| `publish` | 記事 md 生成済み、Hatena 未投稿 | worktree 内で `python scripts/publish_hatena.py <date>` を手動再実行（HTTP エラー等は時間を置く） |
| `git` | 記事 md + Hatena 下書き登録済み | worktree 内で `git add articles/hatena/ && git commit -m "diary: <date> の日記を追加"` → push → PR → merge を手動実施 |
| `cleanup`（worktree 削除のみ失敗） | 全工程完了、worktree のみ残置 | `git -C <親リポ> worktree remove --force <worktree_path>` を手動。`status=ok` のため Slack 通知は成功扱い |

**published.jsonl の重複検知**: 投稿成功時 `published.jsonl` に追記済みのため、同日に再実行すると重複エラーになる。再投稿が必要なら `python scripts/publish_hatena.py <date> --force` で既存エントリを PUT 更新する。

## 無人モード制約

本スキル実行中は `claude -p` 非対話モードでの動作が前提となるため、以下の global rules を **本スキル実行中に限り上書き禁止** する。スキル起動前後・エラー対応中も含めて適用する。

- `AskUserQuestion` 発行禁止（`/triage` 経由・直接発行ともに）
- `code` コマンドによる GUI 起動禁止（subprocess 環境のため機能しない）
- `~/.claude/rules/quality-gate.md` の Phase 2（code-reviewer / doc-reviewer 起動）・Phase 3（QA 実施確認）はスキップ
- 同 Phase 4 の `/auto-finalize` は起動せず、`scripts/auto_publish_diary.py finalize` で commit / push / PR / merge を完結させる
- `~/.claude/rules/invariants.md` のスコープ判断は「Issue 目的に必要なら実行、それ以外はスキップ」で機械的に処理し、`/triage` を呼ばない
- 失敗時は result.json 書き込み + exit 1 のみで終了し、追加の判断・確認・リカバリ提案を行わない

## 注意事項

- 本スキルは **無人実行** が前提。`claude -p` 非対話モードでは `AskUserQuestion` がエラー扱いされるため発行しない
- レビューでの修正適用は `/write-hatena-diary --auto-publish` 内の書き手自己判断に従う
- PR は `gh pr merge --admin --squash` で即マージするため、ブランチ保護ルールがあっても通る。CI 実行は main へのマージ後（post-merge）に発生する想定
- **Phase 3 merge の判定二段化**: `gh pr merge` の exit code が非 0 でも、続けて
  `gh pr view <pr_number> --json state --jq .state` を 1 回呼び、`MERGED` が返れば成功扱いで
  Phase 4 に進む。`MERGED` 以外（取得失敗・タイムアウト含む）は従来通り `failed_phase=git` で
  停止する。リモートはマージ済みなのにローカル副作用で `gh pr merge` が非 0 を返すケース
  （#219）の救済
- **`gh pr merge --admin` 前提**: `gh auth status` で確認できる認証ユーザーが対象リポの Admin 権限を持つこと。becky3 個人リポではオーナー権限で満たすが、組織リポへ移行する場合は権限要件を再確認すること
- 同日二重実行は Phase 0 でブランチ名重複エラー（`failed_phase=environment`）になる。Slack 側で「本日は既に投稿済み」と通知できる
- **PR テンプレ配置の副作用**: `.github/PULL_REQUEST_TEMPLATE/auto-diary.md` は本スキル専用テンプレ。
  - GitHub Web UI から手動 PR を作成すると選択肢に表示される副作用がある。
  - `scripts/auto_publish_diary.py` は本ファイルを読みプレースホルダを展開して `gh pr create --body` に渡すため、CLI 経由では副作用なし。

## 関連

- `scripts/auto_publish_diary.py`: Phase 0・2〜5 のオーケストレーション本体（`setup` / `finalize`）
- `.claude/skills/write-hatena-diary/SKILL.md`: 記事生成スキル本体（`--auto-publish` 経由で呼ぶ）
- `.claude/skills/review-hatena-diary/SKILL.md`: レビュースキル（`--auto-publish` 経由で呼ばれ書き手自己判断）
- `.claude/skills/publish-hatena/SKILL.md`: はてな AtomPub 投稿スキル
- `.github/PULL_REQUEST_TEMPLATE/auto-diary.md`: 自動投稿 PR の本文テンプレ
- `scripts/publish_hatena.py`: AtomPub 投稿スクリプト本体（`finalize` が subprocess 起動 + 純粋関数を import）
- `scripts/write_auto_publish_result.py`: result.json 組み立て・書き込みヘルパー（`finalize` が import）
- `tests/test_auto_publish_diary.py`: orchestrator の単体テスト
- `tests/test_write_auto_publish_result.py`: result.json ヘルパーの単体テスト
