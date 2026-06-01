---
name: delete-hatena
description: はてなブログのエントリとローカル日記記事を AtomPub DELETE で削除する。範囲指定対応。
user-invocable: true
allowed-tools: Bash, Read, Glob
argument-hint: "<YYYY-MM-DD>[..<YYYY-MM-DD>] [--remote-only|--local-only] [--interval <秒>]"
---

## タスク

`articles/hatena/` 配下の日記記事（ローカル md ファイル）と、はてなブログ上の対応エントリを AtomPub DELETE で削除する。`articles/hatena/published.jsonl` の該当行も更新する（デフォルト: 該当行を物理削除 / `--remote-only`: `edit_url` を `null` に書き換え）。

単一日付指定と連続範囲指定（`YYYY-MM-DD..YYYY-MM-DD`）の両方をサポートする。デフォルトはローカル md + はてな側 + jsonl 行の 3 点をまとめて削除する。

仕様: `aidlc-docs/plan-work/issue-178.md`

## 引数

`$ARGUMENTS` の形式:

- **`YYYY-MM-DD`**: 単一日付の削除（必須引数。引数なしはエラー停止）
- **`YYYY-MM-DD..YYYY-MM-DD`**: 連続範囲の削除（開始日 <= 終了日）
- **`--remote-only`**: はてな側 DELETE のみ実行。ローカル md は残し、`published.jsonl` 該当行の `edit_url` を `null` に書き換える
- **`--local-only`**: ローカル md 削除 + `published.jsonl` 該当行削除のみ。はてな側 AtomPub は呼ばない
- **`--interval <秒>`**: はてな DELETE を連続実行する際の各リクエスト間の待機秒数（デフォルト: 1.0）。2 回目以降のはてな DELETE 送信の直前に待機を挟み、バースト送信を避ける。`0` で待機なし。ローカルのみの処理・`edit_url` 未登録の対象は待機しない（実際にはてな DELETE を送信した回数で数えるため、スキップされた対象は待機回数に影響しない）。負値はエラー停止する

### 排他制約

- `--remote-only` と `--local-only` の同時指定はエラー停止する

### 対話確認の責務分離

スクリプト `scripts/delete_hatena.py` は **非対話的に動作する**（呼ばれた時点で削除実行）。削除前の対象確認は本スキル内で **Claude が `AskUserQuestion` で人に確認** する責務を持つ（Phase 2 参照）。スクリプト単体実行時も明示的な呼び出しを意思表示と見なして即実行する。

## 前提条件

| 項目 | 場所 | 内容 |
|---|---|---|
| `HATENA_ID` | リポジトリルートの `.env` | はてなのユーザー名（公開情報。Basic 認証 user 部に使用） |
| `HATENA_API_KEY` | keyring（`service="article-writer"`） | AtomPub 用 API キー |

DELETE は `published.jsonl` の `edit_url` を URL として直接使うため、`HATENA_BLOG_ID` は本スキルでは使用しない（`publish-hatena` 側で必要なため `.env` には残しておく前提）。

`--local-only` 指定時は `.env` / keyring は参照しない（はてな側を呼ばないため）。

## 処理手順

### Phase 0: 環境セットアップ（worktree 対応）

`publish-hatena` と同じ。worktree 内で `.env` が存在しない場合は親リポからコピーする:

```bash
if [ ! -f .env ]; then
  MAIN_REPO=$(git worktree list --porcelain | awk '/^worktree /{sub(/^worktree /,""); print; exit}')
  if [ -n "$MAIN_REPO" ] && [ -f "$MAIN_REPO/.env" ]; then
    cp "$MAIN_REPO/.env" .env
    echo "INFO: 親リポから .env をコピーしました: $MAIN_REPO/.env -> .env"
  fi
fi
```

実行条件はカレントに `.env` が無い場合のみ。親リポにも `.env` が無い場合は初期設定未整備のため、本セクション冒頭の `前提条件` テーブルに従い `.env` を作成してから再実行する。`--local-only` 時は `.env` 不要だが、スキル側では一律でコピーを試みる（コスト最小・副作用なし）。

### Phase 1: 引数パース（Claude 側で実施）

Claude は `$ARGUMENTS` を解析し、以下を確定する:

1. 日付指定の判別:
   - `YYYY-MM-DD`: 単一日付モード
   - `YYYY-MM-DD..YYYY-MM-DD`: 範囲モード（開始 <= 終了であること検証）
   - 上記以外の形式は本スキルを中止し、ユーザーに正しい形式を案内
2. オプション抽出（`--remote-only` / `--local-only` / `--interval <秒>`）。`--remote-only` と `--local-only` の同時指定はエラーで中止
3. モードに応じたメッセージ生成材料（モード名・対象日数）を準備

### Phase 2: 削除対象の事前確認（Claude が AskUserQuestion で人に確認）

Claude は以下を実施する:

1. 日付リスト展開（単一は要素 1、範囲は連続日付の配列に展開）
2. 各日付について `articles/hatena/YYYY-MM-DD-diary.md` の存在を Glob または Read で確認
   - 単一日付指定で md 不在 → エラー中止
   - 範囲指定で md 不在 → 対象から除外し、スキップ一覧として保持
   - 対象が 0 件になった場合（範囲全件スキップ）→ エラー中止
3. 残った対象 md からタイトル（フロントマター `title:`）を抽出
4. `articles/hatena/published.jsonl` を読み、各対象の `edit_url` の有無を判定
5. `--remote-only` 指定時、対象内に `edit_url` が `null`/未登録のエントリがあればエラー中止（はてな側 DELETE 対象がないため）
6. 対象一覧（日付・タイトル・`edit_url` の有無）とモード・スキップ一覧を提示する `AskUserQuestion` を発行する
   - 質問例: 「以下 N 件を削除します。続行しますか？」
   - 選択肢: 「削除を実行」「中止」
7. ユーザーが「中止」を選んだら本スキルを終了する

### Phase 3: 削除実行（スクリプト呼び出し）

ユーザーが Phase 2 で削除を承認したら、`scripts/delete_hatena.py` を呼ぶ:

```bash
python scripts/delete_hatena.py <date_or_range> [--remote-only|--local-only] [--interval <秒>]
```

スクリプトの責務（非対話的に動作。Phase 2 で確認済みのため、呼ばれた時点で削除を実行する）:

1. 引数パース・バリデーション（排他オプション・日付形式・範囲整合性・`--interval` 非負チェック）
2. 日付リスト展開と対象 md 存在確認（Phase 2 と同等のロジックを Claude 側と二重に持つ。スクリプト単体実行時の正しさを担保するため）
3. `--remote-only` 時の事前検証: 対象内に `edit_url` が `null`/未登録のエントリがあればエラー停止
4. `--local-only` 以外: `.env` から `HATENA_ID` を取得し、keyring から `HATENA_API_KEY` を取得する（`HATENA_BLOG_ID` は使用しない）
5. 各対象を順次処理:
   - `--local-only` 以外 & `edit_url` あり → AtomPub DELETE 送信。`--interval` 秒 > 0 のとき、2 回目以降のはてな DELETE 送信の直前に `--interval` 秒待機する
   - `--local-only` 以外 & `edit_url` なし → デフォルトモードでははてな側 DELETE をスキップ（`--remote-only` 時はステップ 3 で事前エラー停止しているため本分岐は通らない）
   - `--remote-only` 以外 → ローカル md 物理削除
   - jsonl 更新: `--remote-only` なら `edit_url` を `null` に書き換え（ステップ 3 の事前検証で `edit_url` 未登録のエントリは弾かれるため、ここに到達する対象は必ず行が存在する）、それ以外なら該当行を物理削除
6. 失敗時の挙動:
   - HTTP 404 / 5xx / ネットワーク失敗で即停止
   - その時点までに完了した処理は確定（jsonl も完了分は書き換え済み）
   - 残りの未実行エントリを一覧表示して exit 1
7. 全件成功時はサマリーを表示

### Phase 4: 結果報告

スクリプトの出力をそのままユーザーに見せる。

成功時の典型出力（Phase 2 の AskUserQuestion でユーザーが「削除を実行」を選んだ後の Phase 3 のスクリプト出力）:

```text
削除対象:
  - 2026-05-13  クロちゃんが配属された日  (edit_url: あり)
モード: ローカル + はてな + jsonl（対象 1 件）
🗑️ 2026-05-13 削除中...
  はてな側 DELETE 成功
  ローカル md 削除: articles/hatena/2026-05-13-diary.md

完了: 1 件
  2026-05-13
✅ 全件削除成功
```

範囲指定でスキップが発生したときの典型出力:

```text
⏭️ スキップ（対象 md が存在しない）: 2026-05-02, 2026-05-04
削除対象:
  - 2026-05-01  ...  (edit_url: あり)
  - 2026-05-03  ...  (edit_url: あり)
  - 2026-05-05  ...  (edit_url: あり)
モード: ローカル + はてな + jsonl（対象 3 件）
...
```

範囲指定中の部分失敗時の典型出力:

```text
🗑️ 2026-05-01 削除中...
  はてな側 DELETE 成功
  ローカル md 削除: articles/hatena/2026-05-01-diary.md
🗑️ 2026-05-02 削除中...

完了: 1 件
  2026-05-01
❌ 失敗で停止: 2026-05-02
  はてな側 DELETE: ✗ 未完了
  ローカル md 削除: - 試行せず
  jsonl 更新: 失敗対象は未反映（完了済み対象のみ反映済み）
  エラー: はてな側にエントリが見つかりません (HTTP 404): ...
未実行 (1 件): 2026-05-03
```

エラー時は終了コード 1 で停止する。

## エラーハンドリング一覧

| ケース | 対応 |
|---|---|
| 日付形式が不正（`YYYY-MM-DD` でも範囲記法でもない） | スクリプトがエラー表示 + 停止 |
| 範囲指定で開始日 > 終了日 | スクリプトがエラー表示 + 停止 |
| `--remote-only` と `--local-only` の同時指定 | スクリプトがエラー表示 + 停止 |
| `--interval` に負値を指定 | スクリプトがエラー表示 + 停止 |
| 単一日付指定で対象 md が存在しない | スクリプトがエラー表示 + 停止 |
| 範囲指定で対象 md が存在しない日付 | スキップ + 一覧表示して残りで続行（対象 0 件ならエラー停止） |
| `--remote-only` で対象に `edit_url` 未登録のエントリ混在 | スクリプトがエラー表示 + 停止（はてな側 DELETE 対象がないため）|
| Phase 2 の AskUserQuestion でユーザーが「中止」を選んだ | Claude が本スキルを終了する（スクリプトは呼ばれない） |
| `.env` 未配置（`--local-only` 以外） | スクリプトがエラー表示 + 停止 |
| keyring に `HATENA_API_KEY` 未登録（`--local-only` 以外） | スクリプトがエラー表示 + 停止 |
| AtomPub DELETE が HTTP 404 | スクリプトがエラー表示 + 即停止。それまで完了した処理は確定、残りは未実行 |
| AtomPub DELETE が HTTP 5xx / ネットワーク失敗 | 同上（404 と同じ即停止挙動） |
| ローカル md の削除で OSError（権限不足等） | 同上（即停止）。はてな側 DELETE が先行で成功している場合、当該エントリの「はてな側削除済み・ローカル/jsonl 未処理」の中間状態が残るため、再実行時は `--local-only` で該当日付を片付ける |
| published.jsonl 書き換えで OSError | `tempfile` 経由の atomic rename を採用しており、書き込み途中の中断ではファイル破損しない。最終 `os.replace` で OSError が発生した場合は例外伝播 → 終了コード 1 で停止し、はてな側 DELETE の成功分が jsonl に反映されない不整合が残る点に注意（再実行時は手動で jsonl を整合させる） |

## 注意事項

- 削除は不可逆操作。はてな側で削除した記事は管理画面からも復旧できない（はてなブログの仕様）
- ローカル md は `git checkout` で復旧可能だが、commit 前の生成済み下書きを誤削除した場合は git では戻せない
- `--remote-only` 後の `published.jsonl` には `edit_url: null` のエントリが残る。再度はてなに投稿したい場合は `publish-hatena` を `--force` なしで実行する（同日エントリで重複停止するため、手動で該当行を削除してから実行する必要がある）
- `--local-only` 後の `published.jsonl` からは該当行が消える。同日付で再投稿する場合は通常の `publish-hatena`（POST）で新規エントリとして登録される
- 範囲指定中の部分失敗時、`published.jsonl` は完了分まで書き換え済み。再実行時は残りの日付のみを範囲指定または個別に指定する
- 本スキルは API キー値・認証情報を出力・記録しない（`~/.claude/rules/invariants.md` 「秘匿情報の出力禁止」遵守）

## 関連

- `scripts/delete_hatena.py`: 削除スクリプト本体
- `scripts/publish_hatena.py`: 流用元（共通関数を import）
- `.claude/skills/publish-hatena/SKILL.md`: 投稿スキル（対称）
- `articles/hatena/published.jsonl`: 投稿履歴台帳（本スキルが更新する）
- `aidlc-docs/plan-work/issue-178.md`: 本スキル新設の計画ファイル（Issue #178）
