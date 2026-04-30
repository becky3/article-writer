---
name: write-zenn
description: Zenn形式の技術記事を生成（候補提案 / テーマ指定の両モード対応）
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, mcp__rag-knowledge-production__rag_list_recent, mcp__rag-knowledge-production__rag_search, mcp__rag-knowledge-production__rag_get_document
argument-hint: "[テーマ]"
---

## タスク

ジャーナル（`rag-knowledge-production` MCP サーバーに `source_type=journal` で取り込み済み）、
GitHub Issue、仕様書、コードから Zenn 形式の記事を生成する。

ジャーナルはローカルファイルではなく RAG 経由で取得するため、
複数リポジトリ横断の知見を素材として活用できる。

仕様書（外部向け概要）: `docs/specs/features/article-generation.md`

## 対象リポジトリ・パス解決

複数リポジトリを横断する素材源（GitHub Issue、ローカル `docs/specs/`）の対象範囲は `.claude/sources.yml` で管理する。

- **設定ファイル**: `.claude/sources.yml`（`repositories:` キーに `<owner>/<name>` 形式で列挙）
- **ローカルパス解決**: 環境変数 `LOCAL_REPOS_ROOT` の値を起点に `${LOCAL_REPOS_ROOT}/<owner>/<name>` を組み立てる
- **`LOCAL_REPOS_ROOT` 未設定時**: スキル実行を停止し、ユーザーに環境変数の設定を依頼する
- **ローカルパスが存在しない場合**: 警告を出してそのリポをスキップし、他リポの処理を続行する

### .tmp 等の出力先解決（worktree 対応）

worktree 内で実行された場合でも、共有資源（`articles/`）は本ワークツリー内の git 管理対象として扱う（コミット → マージで他ワークツリーへ伝搬する想定）。`.tmp/` 等のローカル一時領域は使用しない。

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: トピック候補を自動提案 → ユーザーがチャットで番号を返信 → 記事生成（Phase A → B）
- **`<テーマ>`**: テーマを直接指定 → 素材を自律収集 → 記事生成（Phase B）

テーマは自由文。例:

- `/write-zenn auto-fixワークフローの全体像を紹介する記事`
- `/write-zenn Windows Git Bashでハマったポイント集`
- `/write-zenn auto-fix-workflow-overview.md のドラフトを改善して`

※ 番号での候補選択は Phase A 実行後にチャットで返信する形式。引数に番号を指定する使い方はしない。

## 処理手順

### A. トピック候補提案（引数なし）

1. **ジャーナル一覧の取得**
   - `rag_list_recent(source_type="journal", limit=50)` — RAG に取り込まれたジャーナル一覧
   - `.claude/sources.yml` の `repositories` を読み、各 `<owner>/<name>` の `<name>` 部分を `filters="repository=<name1>,repository=<name2>,..."` 等で絞り込む（フィルタ仕様は MCP 側に従う。複数指定が不可な場合はリポ別に逐次取得する）
   - 各結果の `source_id` 値を控える。以後 `rag_get_document(source_id=...)` には
     この値をそのまま渡す。この時点では本文を取得しない

2. **プロジェクトテーマのスキャン**
   - `.claude/sources.yml` の各リポについて、`${LOCAL_REPOS_ROOT}/<owner>/<name>/docs/specs/` が存在する場合のみ `docs/specs/**/*.md` を読む — 仕様書から記事化できそうなテーマを抽出
   - `.claude/sources.yml` の各リポについて、`gh issue list --repo <owner>/<name> --state closed` を実行して完了済み Issue を取得する

3. **候補絞り込みと本文取得**
   - ステップ 1 のジャーナル一覧（タイトル・published_at）から記事化できそうな候補を絞る
   - 絞った候補のみ `rag_get_document(source_id=...)` で本文を取得する（全件取得は禁止）

4. **トピック抽出ルール**（取得済み本文に対して適用）
   - ジャーナル形式: 本文中の `- **気づき**:` / `- **判断**:` / `- **教訓**:` を検出しトピック候補として抽出
   - プロジェクトテーマ: 仕様書のタイトル・概要、Issue のタイトルから「記事にできそうなテーマ」を抽出
   - 「教訓」「対応」キーワードがあれば優先度UP
   - **自動除外はしない**（過去に記事化したトピックも候補に表示）

5. **候補表示**

   ```text
   📚 学びトピック候補

   ── TIL・ハマりネタ ──
   1. [★★] RSS 1.0形式での日付取得失敗（journal:20260215-xxx）
   2. [★★] skip-summary実装時のコード重複（journal:20260214-xxx）

   ── プロジェクト紹介ネタ ──
   3. auto-fixワークフロー（Issue → 実装 → レビュー → マージの全自動パイプライン）
   4. エージェントチーム機能（複数AIが協調して開発タスクを処理）

   👉 番号を返事してください

   ---
   📰 過去の記事化履歴（参考）
   - (2026-02-10) Pythonでプロセス生存確認を実装したら...: journal:20260210-xxx
   ```

6. **ユーザーの返事を待つ**
   - ユーザーが番号で返事 → Phase B へ進む

### B. 記事生成

Phase A からの番号返信、または `/write-zenn <テーマ>` によるテーマ直接指定、いずれの場合も以下の流れで記事を生成する。

1. **素材の収集**
   - 番号選択の場合: Phase A で控えた `source_id` に対し `rag_get_document(source_id=...)` で本文を取得し、該当セクションを抽出
   - テーマ指定の場合: テーマをキーに関連素材を自律収集
     - GitHub Issue: `.claude/sources.yml` の各リポに対して `gh issue list --repo <owner>/<name>` / `gh issue view --repo <owner>/<name> <番号>` を実行
     - 仕様書: `.claude/sources.yml` の各リポについて `${LOCAL_REPOS_ROOT}/<owner>/<name>/docs/specs/` 配下を Glob/Grep で参照
     - ジャーナル: `rag_search(query=<テーマ>, source_type="journal")` で検索
       → 必要な `source_id` のみ `rag_get_document` で全文取得
     - コード・ワークフロー（テーマに関連するファイル。`.claude/sources.yml` の対象リポのローカルパスを参照）
     - 既存記事（`articles/zenn/` 配下の過去記事）
   - 素材が不足している場合はユーザーに報告し、追加情報を求める

2. **記事タイプの自動判定**
   - 収集した素材を分析し、最適なテンプレートを選択（「記事タイプ自動判定」参照）
   - 判定結果はユーザーに表示して確認を取る

3. **記事生成**
   - 判定タイプに応じたテンプレートファイルと `quality-guidelines.md` を読み込む
   - テンプレートと執筆品質ガイドラインに従い生成
   - スクリーンショット・挿絵が効果的な箇所に画像プレースホルダーを挿入（後述「挿絵・スクリーンショットの指示」参照）

4. **ファイル出力**
   - 出力先: `articles/zenn/{YYYYMMDD-HHMMSS}-{article-slug}.md`（git 管理下）
     - `{YYYYMMDD-HHMMSS}` はファイル作成時のローカル時刻（例: `20260430-114600`）。ジャーナル命名と同様
     - `{article-slug}` は英数字とハイフンのみ。記事タイトルから生成
   - 最初から最終稿の場所で編集する（中間ドラフトを別ディレクトリに置かない）
   - `articles/zenn/published.txt` に日付・タイトル・ソース参照を追記
     - 形式: `- (YYYY-MM-DD) タイトル: ソース参照`

5. **Markdownチェック**
   - 生成した記事に `npx markdownlint-cli2@0.20.0` を実行
   - エラーがあれば修正して再チェック

6. **結果表示**

   ```text
   ✅ 記事を生成しました: articles/zenn/20260430-114600-rss-date-parsing.md
   ```

## 記事タイプ自動判定

ソース内容を分析し、最適な記事タイプを判定する。ユーザーは記事タイプを指定しない。

| シグナル | 判定タイプ |
|---------|-----------|
| 「問題」「エラー」「原因」「解決」「ハマった」 | 課題解決型 |
| 「アーキテクチャ」「全体像」「フロー」「設計」「仕組み」「ワークフロー」 | プロジェクト紹介型 |
| 独立した Tips / ポイントが3つ以上列挙 | ノウハウ型 |
| 上記いずれにも該当しない | 課題解決型（デフォルト） |

判定結果はユーザーに表示して確認を取る。表示例:

```text
📝 記事タイプ: 課題解決型（「ハマった」「エラー」を検出）
  変更する場合はタイプ名を返信してください
```

## 記事テンプレート

判定タイプに応じたテンプレートを参照:

- 課題解決型 → `.claude/skills/write-zenn/template-problem.md`
- プロジェクト紹介型 → `.claude/skills/write-zenn/template-project.md`
- ノウハウ型 → `.claude/skills/write-zenn/template-tips.md`

## 執筆品質ガイドライン

**記事生成前に必ず `.claude/skills/write-zenn/quality-guidelines.md` を読み込むこと。**

## 抽出ロジック詳細

### 優先度スコアリング

候補一覧の並び順に使用する。

| 条件 | スコア加算 |
|------|-----------|
| セクションに「教訓」が含まれる | +2 |
| セクションに「対応」が含まれる | +1 |
| コードブロックが含まれる | +1 |
| 「問題」「原因」キーワードがある | +1 |

### ソース参照形式

`{source_type}:{source_id}` または `{source_type}:{source_id}#{fragment}`

例:

- ジャーナル全体: `journal:20260217-xxx`
- ジャーナル内の特定セクション: `journal:20260217-xxx#3`（3 番目の `###` 見出し）
- 同一ジャーナル内の複数トピックを `published.txt` で区別する用途等にフラグメントを使う

`source_id` は `rag_list_recent` / `rag_search` の結果に含まれる `source_id` 値をそのまま使用する。
`rag_get_document(source_id=...)` で全文取得が可能。フラグメントは記事の参照性のための任意付加。

## エラーハンドリング

- 番号が範囲外:

  ```text
  エラー: 番号 {N} は候補にありません。
  ```

- ジャーナルが見つからない（RAG に取り込まれていない・MCP 接続失敗等）:

  ```text
  ⚠️ ジャーナルが取得できませんでした。
  rag-knowledge-production MCP サーバーへの接続、または source_type="journal" の取り込み状況を確認してください。
  ```

- 素材が不足:

  ```text
  ⚠️ テーマ「{テーマ}」に関連する素材が十分に見つかりませんでした。
  追加情報を教えてください（関連 Issue 番号、ファイルパス等）。
  ```

## 挿絵・スクリーンショットの指示

記事生成時、画面のスクリーンショットや挿絵があると読者の理解を助ける箇所に、画像プレースホルダーを挿入する。

**プレースホルダー形式（blockquote）:**

```markdown
> 📸 **TODO** — 画像の説明
```

**例:**

- `> 📸 **TODO** — PR 画面のコメント部分`
- `> 📸 **TODO** — GitHub Actions のワークフロー実行結果画面`
- `> 📸 **TODO** — エラーメッセージが表示されたターミナル画面`

**使い分けルール:**

- 画面UI・実行結果・エラー画面・操作手順など → blockquote プレースホルダーを使用
- DB関係図・シーケンス図・フローチャートなど技術的な図表 → mermaid コードブロックを使用
- **1 プレースホルダ = 1 画像**: 複数の画像をまとめて書かない。テキストの流れの中に 1 枚ずつ配置する
- 再現可能なものだけ配置する（過去の状態で再現不能なスクショは入れない）
- `{{...}}` 形式は使わない（プレビューで目立たず、差し替え忘れるリスクがある）
- プレースホルダーはユーザーが後から実際の画像に差し替える前提

**効果的な配置箇所:**

- トリガーとなる操作の画面（ラベル付与、ボタン押下など）
- 処理結果の画面（PR 作成後、レビューコメント、マージ後など）
- 説明だけでは伝わりにくい UI の状態（設定画面、ダッシュボード等）
- 「動いている様子」が読者の理解を助ける箇所（ワークフロー実行中、ログ出力など）

## 注意事項

- 生成された記事は必ずレビューしてから公開する
- `published: false` で生成されるため、Zenn上で確認後に `true` に変更
- **記事生成後のチームレビュー（公開前必須）:**
  - 事実確認: 実際に確認した環境・条件と記述が一致しているか
  - 推敲: 技術的な誤りがないか、誤解を招く表現がないか
  - 正直さ: 未確認の内容は「ドキュメントによると」「一般的には」と注記しているか
- Zenn AIからレビュー指摘を受けた場合:
  - 指摘を鵜呑みにせず、技術的妥当性を判断する
  - 妥当な指摘のみ対応し、不要な修正はしない
