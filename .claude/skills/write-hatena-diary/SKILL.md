---
name: write-hatena-diary
description: はてなブログ向けの日記記事を、指定日範囲のジャーナルと Bluesky 投稿を素材に生成する
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Skill, mcp__rag-knowledge-production__rag_list_by_date_range, mcp__rag-knowledge-production__rag_get_document
argument-hint: "[YYYY-MM-DD | MM-DD | <日付>..<日付>] [--auto-publish]"
---

## タスク

指定日のジャーナル（必須）と Bluesky 投稿（補足）を素材に、はてなブログ向けの日記 Markdown を生成する。
**1 日 = 1 記事** が単位。範囲指定の場合は範囲内でジャーナルが存在する各日について独立した記事を 1 つずつ生成する（1 記事に複数日をまとめない）。
執筆ガイド（書き手ペルソナ + 品質ルール）は `.claude/skills/write-hatena-diary/quality-guidelines.md` を最上位 SSoT として参照する（Part 1 が物語世界、Part 2 が品質ルール。`/review-hatena-diary` の 3 観点もこのファイルを機械照合する）。
記事テンプレート（リポジトリマスターテーブル含む）は `.claude/skills/write-hatena-diary/template-diary.md` を SSoT とする。
吹き出し・Bluesky 埋め込みの簡素記法は `.claude/skills/write-hatena-diary/balloon-html.md` を参照。
変換は `/publish-hatena` 投稿時に `scripts/convert_article_html.py` が行う。
本スキルは簡素記法を `articles/hatena/*.md` に書き出すまでを担い、HTML 展開は行わない。

仕様書: `aidlc-docs/inception/requirements/requirements.md`（要件）/ `aidlc-docs/construction/write-hatena-diary/functional-design/design.md`（機能設計）

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: 過去執筆記事最新日の翌日から実行日までを 1 日ずつ前進してジャーナル存在日を探し、最初に見つかった 1 日分の日記 1 記事を生成（auto-next モード）。次のいずれかではエラー停止: (a) `articles/hatena/` に過去記事が無い、(b) 過去執筆記事最新日が実行日以降で探索範囲が空、(c) 探索範囲（過去最新 +1 日 .. 実行日）にジャーナル存在日が無い
- **`<YYYY-MM-DD>`**: 指定日 1 日分の日記 1 記事
- **`<MM-DD>`**: 実行日の年を補完して `YYYY-MM-DD` 扱い、1 記事
- **`<日付>..<日付>`**: 範囲指定。範囲内のジャーナル存在日ごとに 1 記事ずつ生成（複数記事）。両端は独立に補完（`MM-DD` 形式は実行日の年で補完）
  - 例: `5-13` → 当年 5/13 の 1 記事、`2025-12-31..1-03` → 2025-12-31..2026-01-03 のジャーナル存在日ごとに記事
- **`--auto-publish`**: 任意。`/auto-publish-diary` 経由で起動される無人実行モード。日付選定軸（`auto-next` / `single` / `range`）とは直交した独立軸として動作する:
  - Phase 5.5: `/review-hatena-diary <パス> --auto-publish` を渡し、レビュー結果を triage ではなく書き手自己判断で適用させる
  - Phase 6: エディタオープンを省略し、構造化された完了メッセージを出力する
  - 範囲指定（`<日付>..<日付>`）との併用はエラー停止する（auto-publish は呼び出し元 `/auto-publish-diary` からの単一日前提）

## 処理手順 (Phase 1〜6)

範囲指定では Phase 3〜5.5 を **日付ごとに独立して繰り返す**。Phase 1（引数パース）で対象日リストを確定し、Phase 2（素材収集）で範囲一括取得 → 日付ごとに分類した後、ジャーナルが存在する各日について Phase 3〜5.5 をループ実行する。

記事生成（Phase 5）直後に自動レビュー（Phase 5.5）が走り、レビュー結果は `/review-hatena-diary` 内で triage 連携・修正適用まで完結する。

### Phase 1: 引数パース

1. 引数のオプションパース（順序非依存）と日付トークン抽出を以下の手順で行う:
   1. `$ARGUMENTS` を空白で分割し、トークンリストを得る
   2. オプション抽出: トークンリストから `--auto-publish` を見つけたら `AUTO_PUBLISH=1` を設定し、
      当該トークンをリストから除外する。位置はリスト内のどこでもよい
      （先頭・末尾・日付前後を問わない）
   3. 未知オプションのバリデーション: 除外後のリスト内に `--` で始まるトークンが残っていれば
      `エラー: 未知のオプションです: <トークン>` で停止する
   4. 日付トークン抽出: 除外後のリストの最初の非空要素を `RAW_ARG` とする
   5. `AUTO_PUBLISH=1` かつ `RAW_ARG` が範囲指定（`..` を含む）の場合はエラー停止:
      `エラー: --auto-publish は単一日前提のため、範囲指定（<日付>..<日付>）との併用はできません`
2. 空文字列の場合: **auto-next モード**（過去執筆記事最新日の翌日 .. 実行日を探索範囲とする）
   1. `articles/hatena/` を走査し、ファイル名 `YYYY-MM-DD-*.md` から日付を抽出。最も新しい日付を `D_last` とする
   2. 過去記事が 0 件で `D_last` が取得できない場合はエラー停止:

      ```text
      エラー: articles/hatena/ に過去記事が存在しません。初回実行は日付指定（YYYY-MM-DD または範囲指定）で起動してください
      ```

   3. `D_last + 1 日` を `DATE_FROM`、実行日のローカル日付を `DATE_TO` に設定し、`MODE=auto-next` とする
   4. `DATE_FROM > DATE_TO`（過去執筆記事最新日が実行日以降）の場合はエラー停止:

      ```text
      エラー: 過去執筆記事最新日（<D_last>）が実行日以降のため自動探索対象日がありません。日付を明示指定してください
      ```

3. `..` を含む場合: 範囲指定として `<左>..<右>` に分割し、それぞれを `parse_date` で解釈、`MODE=range`、`DATE_FROM` / `DATE_TO` を確定
4. それ以外: 単一指定として `parse_date` を適用、`MODE=single`、`DATE_FROM` と `DATE_TO` に同一の単一日付を設定
5. **対象日リスト構築**: `DATE_FROM` から `DATE_TO` まで（両端 inclusive）の日付を列挙して `TARGET_DATES = [date_1, ..., date_n]` を保持。単一指定の場合は要素 1 つ。auto-next モードは Phase 2 でジャーナル存在日 1 件に絞り込む

**`articles/hatena/` 日付抽出の振る舞い:**

| 入力ファイル名 | 処理 |
|---|---|
| `YYYY-MM-DD-*.md`（先頭 10 文字が日付として有効） | `YYYY-MM-DD` を採用 |
| 上記に合致しない（先頭 10 文字が日付形式でない・存在しない日付） | スキップ（候補から除外） |
| `published.jsonl` 等の Markdown 以外 | 走査対象外 |

Phase 3.0「直前記事の参照」と同じ走査手法を用いる（実装の整合性を保つため）。

**`parse_date` の振る舞い:**

| 入力形式 | 処理 |
|---|---|
| `YYYY-MM-DD`（10 文字、ハイフン位置 4,7） | そのまま採用 |
| `MM-DD` / `M-D` 等（ハイフン 1 個、最大 5 文字） | 実行日の年を補完して `YYYY-MM-DD` に組み立て |
| その他 | エラー停止: `エラー: 日付形式を解釈できません: '<入力>'。YYYY-MM-DD または MM-DD で指定してください` |

**範囲指定のバリデーション:**

| ケース | エラーメッセージ |
|---|---|
| `..` の両端が空 | `エラー: 範囲指定の両端を指定してください` |
| `DATE_FROM > DATE_TO` | `エラー: 範囲の開始日が終了日より後です: <DATE_FROM>..<DATE_TO>` |
| 日付として無効（例: 2026-02-30） | `エラー: 無効な日付です: <入力>` |

### Phase 2: 素材収集（範囲一括取得 + 日付ごと分類）

1. `rag_list_by_date_range(date_from=DATE_FROM, date_to=DATE_TO, source_type="journal", limit=100)` でジャーナル一覧を取得（`limit` は十分大きい値を明示。デフォルト 20 ではジャーナル多い日に取り切れない）
2. 結果を **対象日ごとに分類** し、`JOURNAL_BY_DATE = {date: [journals], ...}` を構築。`rag_list_by_date_range` の応答上限に達した場合は警告を表示してユーザーに範囲縮小を促す
3. **範囲内の全日でジャーナル 0 件の場合は即エラー停止**（Bluesky 取得もスキップ）。`MODE=auto-next` か否かでメッセージを出し分ける:

   `MODE=auto-next` 以外:

   ```text
   エラー: 対象期間（<DATE_FROM>..<DATE_TO>）のジャーナルが見つかりませんでした。
   日記はジャーナルを必須素材としています。日付指定を見直してください。
   ```

   `MODE=auto-next`:

   ```text
   エラー: 過去執筆記事最新日の翌日（<DATE_FROM>）から実行日（<DATE_TO>）までジャーナルが見つかりませんでした。
   日記の素材になるジャーナルがないため執筆を停止します。
   ```

4. ジャーナルが存在する日を `JOURNAL_DATES` として保持し、後続 Phase の対象とする。**`MODE=auto-next` の場合は `JOURNAL_DATES` を日付昇順にソートして最も古い 1 日（= `DATE_FROM` に最も近い 1 日）のみを残し、他は破棄する**（1 回の実行で生成する記事は 1 本に固定）。絞り込んだ日を以下の情報メッセージで通知:

   ```text
   情報: auto-next: <date> を執筆対象として選択しました（過去執筆記事最新日の翌日以降で最初のジャーナル存在日）
   ```

5. 範囲内でジャーナルが存在しない日は警告 + スキップ。`MODE=auto-next` の絞り込みで除外された日はこの警告対象から外す（毎回ノイズになるため）:

   ```text
   警告: <date> はジャーナルが見つからなかったためスキップしました
   ```

6. `JOURNAL_BY_DATE` の全ジャーナルを `rag_get_document(source_id=...)` で全文取得
7. `rag_list_by_date_range(date_from=DATE_FROM, date_to=DATE_TO, source_type="bluesky", limit=100)` で Bluesky 投稿一覧を取得（**本ステップは必須実行**、全日 0 件でも続行）
8. 結果を **対象日ごとに分類** し、`BLUESKY_BY_DATE = {date: [posts], ...}` を構築
9. 各投稿について `rag_get_document(source_id=..., format="original")` で投稿 JSON 全体を取得する。

    **`format="original"` 指定必須**（デフォルトの `format="text"` では本文以外のメタデータが失われ、`cid` 等が取得できない）。

    取得した JSON から以下のフィールドを抽出して Phase 4 で `{{{bluesky ... }}}` 簡素記法ブロックの key=value 値として埋め込む:

    | キー | JSON パス |
    |---|---|
    | `did` | `post.author.did` |
    | `cid` | `post.cid` |
    | `rkey` | `post.uri` の末尾（`at://<did>/app.bsky.feed.post/<rkey>` の `<rkey>` 部分） |
    | `handle` | `post.author.handle` |
    | `display-name` | `post.author.displayName` |
    | `created-at` | `post.record.createdAt` |
    | `text` | `post.record.text` |
    | `lang` | `post.record.langs[0]`（任意。省略時は `{{{bluesky ... }}}` 側のデフォルト `ja` が適用される） |

### Phase 2.5: ループ前準備（共通リソース読み込み）

`quality-guidelines.md` と `template-diary.md` を Read する（**Phase 3〜5.5 のループ全体で 1 回のみ実行**。各日のループ内で再読込しない）。読み込んだ内容は Phase 4（執筆ガイド + テンプレート参照）で共通利用する。

---

**以後の Phase 3〜5.5 は `JOURNAL_DATES` を順に走査し、各日 `d` について独立に実行する。**

### Phase 3.0: 直前記事の参照（当該日 `d`）

当該日 `d` より日付が過去の日記記事のうち最新 1 件（以下「直前記事」）を取得し、Phase 4 の生成時の文脈として保持する。

1. `articles/hatena/` 配下のファイル名（`YYYY-MM-DD-*.md`）から、`d` より日付が過去のファイルをすべて列挙する（範囲指定モードで同ループ内に既に Write 済みの記事もここで自然に拾われる）
2. 日付で降順ソートし、先頭 1 件（直前記事）を選択
3. 0 件の場合: Phase 3 へ進む（直前記事なし）
4. 選択した記事を Read する → Phase 3 へ進む

直前記事を Phase 4 で執筆判断にどう活かすかは `quality-guidelines.md` Part 1「直前記事との連続性」を参照。

### Phase 3: Bluesky 選別（当該日 `d`）

1. `BLUESKY_BY_DATE[d]` が 0 件なら本 Phase をスキップして Phase 4 へ
2. 各投稿について、AI / LLM / 開発関連の話題か Claude の文脈理解で判定する
3. 関連と判定した投稿のみ当該日の「引用候補」セットに残す
4. 関連投稿が 0 件の場合: Phase 4 では当該日の Bluesky 引用シーンを設けない

### Phase 4: 記事生成（当該日 `d`）

1. **本文の構成・口調・展開は `quality-guidelines.md` Part 1（物語世界）を制御点として書き手の裁量に任せる**。固定セクション・必須サブセクションは設けない
2. **タイトル** の文字列は `quality-guidelines.md` Part 2「タイトル」の方針に従って決め、フロントマター `title:` と本文 H1 を一致させる
3. **リポを言及する箇所では `name` を backtick 付きで本文に直接書く**（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式・`#<番号>` 形式（Issue / PR）は使わない
4. **吹き出し** は `kuro-chan>>...` / `nee-san>>...` の単行マーカー記法で書く。記法仕様は `balloon-html.md` を参照。HTML タグ（`<div class="balloon">` 等）を直接書かない
5. **Bluesky 引用部** は `{{{bluesky ... }}}` のフェンス記法で書く
    - 記法仕様: `balloon-html.md` 「Bluesky 記法」
    - メタデータ: Phase 2 で取得した key=value 形式（`did` / `cid` / `rkey` / `handle` / `display-name` / `created-at` / `text`、`lang` は任意）
    - 引用部の前提・関係性: `quality-guidelines.md` Part 1「オーナー（社長）の位置づけ」「社長の SNS（Bluesky）について」を参照
6. **簡素記法ブロックの自己チェック**: シーンを書き終えるたびに `balloon-html.md` 「書き手向けチェックリスト」を確認する（balloon の 1 行 1 セリフ / bluesky フェンスの閉じ `}}}` / 入れ子禁止 等）。記事全体を書き終えてからまとめてチェックすると修正箇所が散らばるため、シーン単位で確認する
7. **セクション配置の順序**: タイトル H1 の直下に **登場人物セクション** を置き、続いて本文の H2 シーン、記事末尾に **プロジェクトの説明セクション** を置く。順序の SSoT は `template-diary.md` 冒頭の構造リストを参照
8. **登場人物セクション** をタイトル H1 直下に挿入する（言及リポ・対話シーン数に関わらず常に挿入）。固定 HTML 文言と置換ルールの SSoT は `template-diary.md` 「登場人物セクション」（マーカー全置換義務・字数・改変禁止範囲を含む）。置換内容の方針は `quality-guidelines.md` Part 1「登場人物セクションの一言」を参照
9. **プロジェクトの説明セクション** を記事末尾に挿入する（言及リポの有無に関わらず常に挿入）。セクション構造とテーブル絞り込みルールは `template-diary.md` 「リポジトリマスターテーブル」「プロジェクトの説明セクション」を参照

### Phase 5: ファイル出力（当該日 `d`）

1 日 1 記事を前提とした命名で、`published.jsonl` の重複検知（`date:` キー）と整合する。

1. **出力先パス**: `articles/hatena/{YYYY-MM-DD}-diary.md`
2. ディレクトリが存在しなければ作成
3. **新規作成のため Write を使用**
4. 同名ファイルが既に存在する場合はエラー停止
5. 生成済みパスを `GENERATED_PATHS` リストに追加

### Phase 5.5: レビュー自動呼び出し（当該日 `d`）

Phase 5 で当該日の記事を Write した直後、本ステップで `/review-hatena-diary` を自動呼び出しする。各記事のループ内で実行することで、生成 → review → triage → 修正 をコンテキストが新鮮なうちに完結させる。

1. `Skill` ツールで `/review-hatena-diary <パス>` を起動する。
   - `<パス>` には Phase 5 で Write した記事のリポジトリルートからの相対パス（例: `articles/hatena/2026-05-13-diary.md`）を指定する
   - `/review-hatena-diary` は絶対パス指定をエラー停止するため必ず相対パスで渡す
   - `AUTO_PUBLISH=1` の場合は引数末尾に `--auto-publish` を付与し、`/review-hatena-diary <パス> --auto-publish` の形で起動する
2. `/review-hatena-diary` 内で 3 観点並列レビュー → 指摘の triage 連携 / 書き手自己判断 → 確定した修正を対象記事ファイルへ適用する処理が完結する（本スキル側で追加の triage や修正適用は行わない）
3. `/review-hatena-diary` が正常完了したら次の日のループ（Phase 3）へ進む

エラー時の挙動:

- `/review-hatena-diary` が正常終了しなかった場合（起動自体の失敗・内部停止・全サブエージェント失敗等を含む）は、警告を表示してその日のループを完了扱いとし、次の日のループに進む。生成済み記事は `GENERATED_PATHS` に残る
- **単一日対象モード**（`MODE=single` / `MODE=auto-next`）で「次の日」が存在しない場合はそのまま Phase 6（後処理）へ進む
- `/review-hatena-diary` 内のサブエージェント部分失敗・triage 中断・修正適用失敗は `/review-hatena-diary` 側で処理され、本ステップにはエラーとして伝播しない（部分的な review 結果として完了扱い）

---

**ループ終了後（全 `JOURNAL_DATES` を処理した後）に Phase 6 を 1 回実行する。**

### Phase 6: 後処理（ループ後にまとめて 1 回）

`articles/hatena/**` は markdownlint の対象外のため、本 Phase では lint を実行しない。挙動は `AUTO_PUBLISH` の値で分岐する。

#### `AUTO_PUBLISH=0`（通常モード）

1. `code "<絶対パス1>" "<絶対パス2>" ...` でまとめてエディタを起動（PATH 不通時はサイレントスキップ）
2. 完了メッセージ。単一記事の場合:

   ```text
   ✅ 日記を生成しました: articles/hatena/2026-05-13-diary.md
   ```

   複数記事の場合（範囲指定）:

   ```text
   ✅ 日記を 3 記事生成しました:
     - articles/hatena/2026-05-10-diary.md
     - articles/hatena/2026-05-12-diary.md
     - articles/hatena/2026-05-13-diary.md
   ```

   スキップ日があれば末尾に併記する（例: `（2026-05-11 はジャーナルなしでスキップ）`）

#### `AUTO_PUBLISH=1`（無人モード）

エディタオープンは行わない。`/auto-publish-diary` が後続 Phase でパースする前提の構造化メッセージを出力する:

```text
✅ /write-hatena-diary 完了（auto-publish）
📁 生成記事: articles/hatena/2026-05-13-diary.md
```

複数生成された場合（範囲との誤併用時）は 1 行 1 ファイルで列挙する。`/auto-publish-diary` はこのうち単一日対象の 1 ファイルを期待する。

## 投稿（別スキル）

本スキルは記事生成までを担う。はてなブログへの下書き登録は `/publish-hatena` スキル（`.claude/skills/publish-hatena/SKILL.md`）で行う。`/publish-hatena` が `articles/hatena/published.jsonl` への記録追記も担当する。

**前提**: 1 日 1 記事。`published.jsonl` の重複検知は記事フロントマターの `date:`（日記対象日）を使う。複数日まとめて公開しても日記対象日で識別される。

## エラーハンドリング一覧

| ケース | 対応 |
|---|---|
| 引数の日付形式が不正 | エラーメッセージ表示 + 停止 |
| 未知のオプション（`--auto-publish` 以外の `--` 始まりトークン） | エラーメッセージ表示 + 停止 |
| `--auto-publish` と範囲指定の併用 | エラーメッセージ表示 + 停止（auto-publish は単一日前提） |
| 範囲指定の順序逆転 | エラーメッセージ表示 + 停止 |
| auto-next モードで `articles/hatena/` に過去記事が 0 件 | エラー表示 + 停止（日付指定を促す） |
| auto-next モードで過去執筆記事最新日が実行日以降 | エラー表示 + 停止（探索対象日なし） |
| `rag_list_by_date_range` 接続失敗 | `エラー: rag-knowledge-production MCP への接続を確認してください` 表示 + 停止 |
| 範囲内の全日でジャーナル 0 件 | エラー表示 + 停止（日記成立条件不足。auto-next モードは専用メッセージ） |
| 範囲内の一部の日でジャーナル 0 件 | 警告表示 + その日をスキップして続行 |
| 特定日で Bluesky 検索結果 0 件 | Phase 3 をスキップ + 当該記事の Bluesky セクションを省略して続行 |
| Phase 3〜5.5 ループ中に MCP タイムアウト・致命エラーで全体中断 | それまでに Write 済みのパスを `GENERATED_PATHS` に残し、Phase 6（エディタオープン・完了メッセージ）を残存分に対して実行する。完了メッセージで中断した旨を併記 |
| Phase 5.5 で `/review-hatena-diary` が正常終了しなかった | 警告表示 + その日のループを完了扱いとし、次の日のループに進む（起動失敗・内部停止・全サブエージェント失敗を含む）。単一日対象モード（`MODE=single` / `MODE=auto-next`）で「次の日」が存在しない場合は Phase 6 へ進む |
| `code` PATH 不通 | サイレントスキップ |

## ソース参照形式

`{source_type}:{source_id}` または `{source_type}:{source_id}#{fragment}`

例:

- ジャーナル全体: `journal:journal/agent-commons/20260513-...md`
- ジャーナル内の特定セクション: `journal:journal/agent-commons/20260513-...md#3`（3 番目の `###` 見出し）

`source_id` は `rag_list_by_date_range` / `rag_search` の結果に含まれる `Source` 値をそのまま使用する。
`rag_get_document(source_id=...)` で全文取得が可能。

## 記法ポリシー

詳細は `quality-guidelines.md` Part 2「記法」を SSoT とする。

## NFR と将来拡張

- **AtomPub 自動投稿**: `/publish-hatena` で下書き登録のみサポート。公開投稿（`<app:draft>no</app:draft>`）は別 Issue で扱う

## 注意事項

- 生成された記事は Phase 5.5 で `/review-hatena-diary` による自動レビュー（3 観点並列 + triage + 修正適用）を経た上で出力される
- ペルソナ調整提案は記事生成中に行ってよいが、適用前にオーナー確認を取る（`quality-guidelines.md` 「ペルソナ調整に関する自己制御」参照）
- 著作物・IP 情報の混入を避ける（`quality-guidelines.md` 「著作物・IP 情報の混入防止」参照。`/review-hatena-diary` 観点 2「ガイドライン準拠」でも検出する）
