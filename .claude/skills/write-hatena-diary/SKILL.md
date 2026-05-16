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
執筆ガイド（書き手ペルソナ + 品質ルール）は `.claude/skills/write-hatena-diary/quality-guidelines.md` を最上位 SSoT として参照する（Part 1 が物語世界、Part 2 が品質ルール。`/multi-perspective-review` のガイドライン準拠チェック観点も同ファイルの Part 2 を参照する）。
記事テンプレート（リポジトリマスターテーブル含む）は `.claude/skills/write-hatena-diary/template-diary.md` を SSoT とする。
吹き出し・Bluesky 埋め込みの簡素記法は `.claude/skills/write-hatena-diary/balloon-html.md` を参照。
変換は `/publish-hatena` 投稿時に `scripts/convert_article_html.py` が行う。
本スキルは簡素記法を `articles/hatena/*.md` に書き出すまでを担い、HTML 展開は行わない。

仕様書: `aidlc-docs/inception/requirements/requirements.md`（要件）/ `aidlc-docs/construction/write-hatena-diary/functional-design/design.md`（機能設計）

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: 実行日を対象として 1 日分の日記 1 記事を生成
- **`<YYYY-MM-DD>`**: 指定日 1 日分の日記 1 記事
- **`<MM-DD>`**: 実行日の年を補完して `YYYY-MM-DD` 扱い、1 記事
- **`<日付>..<日付>`**: 範囲指定。範囲内のジャーナル存在日ごとに 1 記事ずつ生成（複数記事）。両端は独立に補完（`MM-DD` 形式は実行日の年で補完）
  - 例: `5-13` → 当年 5/13 の 1 記事、`2025-12-31..1-03` → 2025-12-31..2026-01-03 のジャーナル存在日ごとに記事

## 処理手順 (Phase 1〜6)

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
9. 各投稿について `rag_get_document(source_id=...)` で全文取得し、メタデータ（DID / CID / handle / display_name / rkey / created_at / 本文 / lang）を抽出する。Phase 4 で `:::bluesky` 簡素記法ブロックの key=value 値として埋め込む

### Phase 2.5: ループ前準備（共通リソース読み込み）

`quality-guidelines.md` と `template-diary.md` を Read する（**Phase 3〜5 のループ全体で 1 回のみ実行**。各日のループ内で再読込しない）。読み込んだ内容は Phase 4（執筆ガイド + テンプレート参照）で共通利用する。

---

**以後の Phase 3〜5 は `JOURNAL_DATES` を順に走査し、各日 `d` について独立に実行する。**

### Phase 3: Bluesky 選別（当該日 `d`）

1. `BLUESKY_BY_DATE[d]` が 0 件なら本 Phase をスキップして Phase 4 へ
2. 各投稿について、AI / LLM / 開発関連の話題か Claude の文脈理解で判定する
3. 関連と判定した投稿のみ当該日の「引用候補」セットに残す
4. 関連投稿が 0 件の場合: Phase 4 では当該日の Bluesky 引用シーンを設けない

### Phase 4: 記事生成（当該日 `d`）

1. **本文の構成・口調・展開は `quality-guidelines.md` Part 1（物語世界）を制御点として書き手の裁量に任せる**。固定セクション・必須サブセクションは設けない
2. **タイトル** の文字列は `quality-guidelines.md` Part 2「タイトル」の方針に従って決め、フロントマター `title:` と本文 H1 を一致させる
3. **リポを言及する箇所では `name` を backtick 付きで本文に直接書く**（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式・`#<番号>` 形式（Issue / PR）は使わない
4. **吹き出し** は `:::kuro-chan` / `:::nee-san` の簡素記法で書く。記法仕様は `balloon-html.md` を参照。HTML タグ（`<div class="balloon">` 等）を直接書かない
5. **Bluesky 引用部** は `:::bluesky` 簡素記法で書く
    - 記法仕様: `balloon-html.md` 「Bluesky 記法」
    - メタデータ: Phase 2 で取得した key=value 形式（`did` / `cid` / `rkey` / `handle` / `display-name` / `created-at` / `text`、`lang` は任意）
    - 引用部の前提・関係性: `quality-guidelines.md` Part 1「オーナー（社長）の位置づけ」「社長の SNS（Bluesky）について」を参照
6. **簡素記法ブロックの自己チェック**: シーンを書き終えるたびに `balloon-html.md` 「書き手向けチェックリスト」を確認する（H2 直前の閉じ忘れ / 入れ子禁止 等）。記事全体を書き終えてからまとめてチェックすると修正箇所が散らばるため、シーン単位で確認する
7. **冒頭セクションの順序**: タイトル H1 の直下に **登場人物セクション** を最初に置き、その直下に **プロジェクトの説明セクション** を置く。続いて本文最初の H2 シーンへ繋げる。順序の SSoT は `template-diary.md` 「冒頭セクションの順序」を参照
8. **登場人物セクション** をタイトル H1 直下に挿入する（言及リポ・対話シーン数に関わらず常に挿入）。固定 HTML 文言と置換ルールの SSoT は `template-diary.md` 「登場人物セクション」（マーカー全置換義務・字数・改変禁止範囲を含む）。置換内容の方針は `quality-guidelines.md` Part 1「登場人物セクションの一言」を参照
9. **プロジェクトの説明セクション** を登場人物セクションの直下に挿入する（言及リポの有無に関わらず常に挿入）。固定文言は `template-diary.md` 「プロジェクトの説明セクション」を参照
10. **執筆品質の自己チェック**: 記事全体を書き終えたら、以下のフローで自己チェックする。観点別の列挙ではなく、関連ドキュメントを **改めて Read してから** 記事を読み直して問題点を洗い出す方式に統一する
    1. `quality-guidelines.md` を Read で読み直す（Part 1 / Part 2 を通読）
    2. 生成した記事 markdown を Read で読み直す
    3. ガイドの各項目と記事本文を逐次照合し、違反・乖離・違和感のある箇所を洗い出す
    4. 検出した問題点を Edit で修正する（マーカー残存・キャラ口調・カッコ書き・内部実装語頻度・登場人物セクションの一言整合 等、すべて対象）

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

## 投稿（別スキル）

本スキルは記事生成までを担う。はてなブログへの下書き登録は `/publish-hatena` スキル（`.claude/skills/publish-hatena/SKILL.md`）で行う。`/publish-hatena` が `articles/hatena/published.txt` への記録追記も担当する。

**前提**: 1 日 1 記事。`published.txt` の重複検知は記事フロントマターの `date:`（日記対象日）を使う。複数日まとめて公開しても日記対象日で識別される。

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

- **AtomPub 自動投稿**: `/publish-hatena` で下書き登録のみサポート。公開投稿（`<app:draft>no</app:draft>`）は別 Issue で扱う

## 注意事項

- 生成された記事は必ずレビューしてから公開する
- 観点別並列レビューが必要な場合は `/multi-perspective-review <記事ファイルパス>` の実行を推奨する（自動呼び出しはせず、ユーザー判断で起動）。`articles/hatena/` 配下の記事を渡せば、本スキル用の `quality-guidelines.md` を参照して 5 観点フルレビューが走る
- ペルソナ調整提案は記事生成中に行ってよいが、適用前にオーナー確認を取る（`quality-guidelines.md` 「ペルソナ調整に関する自己制御」参照）
- 著作物・IP 情報の混入を避ける（`quality-guidelines.md` 「著作物・IP 情報の混入防止」参照）
