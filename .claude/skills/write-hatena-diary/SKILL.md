---
name: write-hatena-diary
description: はてなブログ向けの日記記事を、指定日範囲のジャーナルと Bluesky 投稿を素材に生成する
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, mcp__rag-knowledge-production__rag_list_by_date_range, mcp__rag-knowledge-production__rag_get_document
argument-hint: "[YYYY-MM-DD] or [MM-DD] or [<日付>..<日付>]"
---

## タスク

指定日のジャーナル（必須）と Bluesky 投稿（補足）を素材に、はてなブログ向けの日記 Markdown を生成する。
**1 日 = 1 記事** が単位。範囲指定の場合は範囲内でジャーナルが存在する各日について独立した記事を 1 つずつ生成する（1 記事に複数日をまとめない）。
書き手のペルソナは `.claude/skills/write-hatena-diary/persona.md` で定義され、本スキルから参照する。
記事テンプレート（リポジトリマスターテーブル含む）は `.claude/skills/write-hatena-diary/template-diary.md` を SSoT とする。
執筆品質ガイドラインは `.claude/skills/write-hatena-diary/quality-guidelines.md` を参照する（`/multi-perspective-review` のガイドライン準拠チェック観点もこのファイルを参照する）。

仕様書: `aidlc-docs/inception/requirements/requirements.md`（要件）/ `aidlc-docs/construction/write-hatena-diary/functional-design/design.md`（機能設計）

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: 実行日を対象として 1 日分の日記 1 記事を生成
- **`<YYYY-MM-DD>`**: 指定日 1 日分の日記 1 記事
- **`<MM-DD>`**: 実行日の年を補完して `YYYY-MM-DD` 扱い、1 記事
- **`<日付>..<日付>`**: 範囲指定。範囲内のジャーナル存在日ごとに 1 記事ずつ生成（複数記事）。両端は独立に補完（`MM-DD` 形式は実行日の年で補完）
  - 例: `5-13` → 当年 5/13 の 1 記事、`2025-12-31..1-03` → 2025-12-31..2026-01-03 のジャーナル存在日ごとに記事

## 処理手順 (Phase 1〜6 + 公開後処理)

範囲指定では Phase 3〜5 を **日付ごとに独立して繰り返す**。Phase 1（引数パース）で対象日リストを確定し、Phase 2（素材収集）で範囲一括取得 → 日付ごとに分類した後、ジャーナルが存在する各日について Phase 3〜5 をループ実行する。

### Phase 1: 引数パース

1. `$ARGUMENTS` を空白で分割し、最初の非空トークンを `RAW_ARG` とする
2. 空文字列の場合: `MODE=today`、`DATE_FROM` と `DATE_TO` に実行日のローカル日付を設定
3. `..` を含む場合: 範囲指定として `<左>..<右>` に分割し、それぞれを `parse_date` で解釈、`MODE=range`、`DATE_FROM` / `DATE_TO` を確定
4. それ以外: 単一指定として `parse_date` を適用、`MODE=single`、`DATE_FROM` と `DATE_TO` に同一の単一日付を設定
5. **対象日リスト構築**: `DATE_FROM` から `DATE_TO` まで（両端 inclusive）の日付を列挙して `TARGET_DATES = [date_1, ..., date_n]` を保持。単一指定/今日扱いの場合は要素 1 つ

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
3. **範囲内の全日でジャーナル 0 件の場合は即エラー停止**（Bluesky 取得もスキップ）:

   ```text
   ⚠️ 対象期間（<DATE_FROM>..<DATE_TO>）のジャーナルが見つかりませんでした。
   日記はジャーナルを必須素材としています。日付指定を見直してください。
   ```

4. ジャーナルが存在する日を `JOURNAL_DATES` として保持し、後続 Phase の対象とする
5. 範囲内でジャーナルが存在しない日は警告 + スキップ:

   ```text
   ⚠️ <date> はジャーナルが見つからなかったためスキップしました
   ```

6. `JOURNAL_BY_DATE` の全ジャーナルを `rag_get_document(source_id=...)` で全文取得
7. `rag_list_by_date_range(date_from=DATE_FROM, date_to=DATE_TO, source_type="bluesky", limit=100)` で Bluesky 投稿一覧を取得（**本ステップは必須実行**、全日 0 件でも続行）
8. 結果を **対象日ごとに分類** し、`BLUESKY_BY_DATE = {date: [posts], ...}` を構築
9. 各投稿について `rag_get_document(source_id=...)` で全文取得し、メタデータ（DID / CID / handle / display_name / rkey / created_at / 本文 / lang）を抽出する。Phase 4 で HTML 埋め込みスニペット生成スクリプトに渡す引数として保持

### Phase 2.5: ループ前準備（共通リソース読み込み）

`persona.md` と `template-diary.md` を Read する（**Phase 3〜5 のループ全体で 1 回のみ実行**。各日のループ内で再読込しない）。読み込んだ内容は Phase 4（ペルソナ + テンプレート参照）で共通利用する。

---

**以後の Phase 3〜5 は `JOURNAL_DATES` を順に走査し、各日 `d` について独立に実行する。**

### Phase 3: Bluesky 選別（当該日 `d`）

1. `BLUESKY_BY_DATE[d]` が 0 件なら本 Phase をスキップして Phase 4 へ
2. 各投稿について、AI / LLM / 開発関連の話題か Claude の文脈理解で判定する
3. 関連と判定した投稿のみ当該日の「引用候補」セットに残す
4. 関連投稿が 0 件の場合: 当該記事の「オーナーの Bluesky 投稿への反応」セクションを Phase 4 で省略する

### Phase 4: 記事生成（当該日 `d`）

1. **タイトル**を当該日のジャーナル内容を要約した 20〜30 文字程度の自然な日本語で生成する。日付は含めない（フロントマター・ファイル名で表現済み）。例: 「ジャーナル機能の追加とリポ呼称ルールの整備」
2. **`template-diary.md` の「記事本文セクション雛形」群** に従って当該日 1 つ分の記事を組み立てる（セクション順序・必須/条件付き判定はテンプレート側を SSoT として参照）
3. ペルソナ自己呼称・オーナー呼称・トーン使い分けは `persona.md` の規定に従う
4. **リポを言及する箇所では `name` を backtick 付きで本文に直接書く**（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式・`#<番号>` 形式（Issue / PR）は使わない
5. **Bluesky 引用部** は `scripts/generate_bluesky_embed.py` で生成した HTML 埋め込みスニペットを Markdown 本文に直接挿入する（雛形は `template-diary.md` 「Bluesky 引用フォーマット」を参照）。
   各投稿について Phase 2 で取得したメタデータを CLI 引数に渡して呼ぶ:
   `--did` / `--cid` / `--rkey` / `--handle` / `--display-name` / `--text` / `--created-at` / `--lang`（任意）。
   詳細は `python scripts/generate_bluesky_embed.py --help` を参照
6. **「結果」項目は独立セクション化しない**。`### 概要` または `### うまくいった / ハマった` の文章に溶け込ませる
7. **末尾固定セクション** として `## プロジェクトの説明` を挿入する。リポジトリの個別説明は外部記事に集約されており、本セクションでは固定文言 + 外部記事リンクのみ記載する（雛形は `template-diary.md` の「## プロジェクトの説明 (末尾固定)」を参照）。言及リポの有無に関わらず常に挿入する

### Phase 5: ファイル出力（当該日 `d`）

1. **slug 生成**: Phase 4 で確定した記事タイトル（日本語）を英訳しハイフン区切りに整形。**slug には日付を含めない**（日付はファイル名先頭部分で表現済み）。例: 「ジャーナル機能の追加とリポ呼称ルールの整備」→ `journal-feature-and-repo-alias-rules`
2. **出力先パス**: `articles/hatena/{d}-{HH-MM-SS}-{slug}.md`
   - `{d}` は当該記事の日記対象日
   - `{HH-MM-SS}` は **本記事の Write 直前に取得するローカル時刻**（`date +%H-%M-%S` 相当。連続生成でも各記事ごとに取得することで秒単位で衝突しない）
3. ディレクトリが存在しなければ作成
4. **新規作成のため Write を使用**。最初から最終稿の場所で編集する（中間ドラフトを別ディレクトリに置かない）
5. 生成済みパスを `GENERATED_PATHS` リストに追加

---

**ループ終了後（全 `JOURNAL_DATES` を処理した後）に Phase 6 を 1 回実行する。**

### Phase 6: 後処理（ループ後にまとめて 1 回）

`articles/hatena/**` は markdownlint の対象外（`template-diary.md` 「記法ポリシー」セクション参照）のため、本 Phase では lint を実行しない。エディタオープンと完了メッセージ表示のみを行う。

1. `code "<絶対パス1>" "<絶対パス2>" ...` でまとめてエディタを起動（PATH 不通時はサイレントスキップ）
2. 完了メッセージ。単一記事の場合:

   ```text
   ✅ 日記を生成しました: articles/hatena/2026-05-13-114600-journal-feature-and-repo-alias-rules.md
   ```

   複数記事の場合（範囲指定）:

   ```text
   ✅ 日記を 3 記事生成しました:
     - articles/hatena/2026-05-10-114600-journal-feature-and-repo-alias-rules.md
     - articles/hatena/2026-05-11-114602-template-refresh-doc-overhaul.md
     - articles/hatena/2026-05-12-114604-diary-skill-design.md
   ```

   スキップ日があれば末尾に併記する（例: `（2026-05-11 はジャーナルなしでスキップ）`）

## 公開後処理（別フロー、ユーザー指示時のみ）

ユーザーから「公開した」「Hatena に上げた」等の指示を受けたタイミングで実行する。

1. 公開後の最終タイトルを確認（ユーザー指定または公開済み記事を直接参照）
2. `articles/hatena/published.txt` に追記:
   - 形式: `- (YYYY-MM-DD) タイトル: ソース参照`
   - `YYYY-MM-DD` は公開日（日記対象日ではない点に注意）
   - ソース参照は `journal:...` / `bluesky:...` を併記
3. 既存記事のタイトルが公開時に変更されていた場合、対応する `published.txt` 行も合わせて更新する

**MVP の前提**: 同日に複数記事を公開するケースは想定しない。`published.txt` の行特定は日付キーを使うため、同日複数記事が発生すると行特定が曖昧になる。複数日まとめての公開や同日複数記事公開が必要になった場合は別 Issue で対応する。

## エラーハンドリング一覧

| ケース | 対応 |
|---|---|
| 引数の日付形式が不正 | エラーメッセージ表示 + 停止 |
| 範囲指定の順序逆転 | エラーメッセージ表示 + 停止 |
| `rag_list_by_date_range` 接続失敗 | `⚠️ rag-knowledge-production MCP への接続を確認してください` 表示 + 停止 |
| 範囲内の全日でジャーナル 0 件 | エラー表示 + 停止（日記成立条件不足） |
| 範囲内の一部の日でジャーナル 0 件 | 警告表示 + その日をスキップして続行 |
| 特定日で Bluesky 検索結果 0 件 | Phase 3 をスキップ + 当該記事の Bluesky セクションを省略して続行 |
| Phase 3〜5 ループ中に MCP タイムアウト・致命エラーで全体中断 | それまでに Write 済みのパスを `GENERATED_PATHS` に残し、Phase 6（エディタオープン・完了メッセージ）を残存分に対して実行する。完了メッセージで中断した旨を併記 |
| `code` PATH 不通 | サイレントスキップ |

## ソース参照形式

`{source_type}:{source_id}` または `{source_type}:{source_id}#{fragment}`

例:

- ジャーナル全体: `journal:journal/agent-commons/20260513-...md`
- ジャーナル内の特定セクション: `journal:journal/agent-commons/20260513-...md#3`（3 番目の `###` 見出し）

`source_id` は `rag_list_by_date_range` / `rag_search` の結果に含まれる `Source` 値をそのまま使用する。
`rag_get_document(source_id=...)` で全文取得が可能。

## 記法ポリシー

詳細は `template-diary.md` の「記法ポリシー」セクションを SSoT とする。要点のみ再掲:

- GitHub-flavored Markdown（GFM）のみで記述。はてな記法は不使用
- 絵文字は Unicode 直接記述（ショートコード形式は不使用）
- 運用前提: はてなブログ側のデフォルト編集モードを「Markdown」に設定しておく必要がある

## NFR と将来拡張

- **シークレット管理 (MVP 外)**: Phase C（はてなブログ AtomPub への自動投稿）は本 MVP に含めない。将来実装する際は ai-assistant / py-common-lib に倣い、`py_common_lib.get_secret(key, service="article-writer")` 経由で OS のセキュアストレージ（keyring）から取得する。環境変数フォールバックは行わない
- **AtomPub 投稿時の Content-Type (MVP 外)**: Phase C で AtomPub に投稿する際は、XML 中の `<content>` 要素に `type="text/x-markdown"` を指定して Markdown を直接送信する。これにより、はてなブログのデフォルト編集モード設定にかかわらず Markdown 本文として登録できる
- **Bluesky 投稿者フィルタ (MVP 外)**: 現時点では rag-knowledge 側にオーナーの投稿のみが取り込まれているためフィルタ不要。将来他者投稿の取り込みが始まったら、オーナー DID（または handle）でのフィルタを追加する（別 Issue で対応）

## 注意事項

- 生成された記事は必ずレビューしてから公開する
- 観点別並列レビューが必要な場合は `/multi-perspective-review <記事ファイルパス>` の実行を推奨する（自動呼び出しはせず、ユーザー判断で起動）。`articles/hatena/` 配下の記事を渡せば、本スキル用の `quality-guidelines.md` を参照して 5 観点フルレビューが走る
- ペルソナ調整提案は記事生成中に行ってよいが、適用前にオーナー確認を取る（`quality-guidelines.md` 「ペルソナ調整に関する自己制御」参照）
- 著作物・IP 情報の混入を避ける（`quality-guidelines.md` 「著作物・IP 情報の混入防止」参照）
