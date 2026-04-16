# article-writer

開発ジャーナル・仕様書・Issue 等の開発知見から技術記事を生成する Claude Code スキル。

現在は Zenn 形式に対応。将来的に note 等のプラットフォームにも拡張予定。

## 機能

- ジャーナル・MEMORY.md からトピック候補を自動抽出
- 記事タイプの自動判定（課題解決型 / プロジェクト紹介型 / ノウハウ型）
- テンプレートと品質ガイドラインに基づく記事生成
- 執筆品質チェック（markdownlint）

## 使い方

Claude Code セッション内で `/topic` コマンドを実行する。

```
# トピック候補を自動提案
/topic

# テーマを直接指定して記事生成
/topic Windows Git Bashでハマったポイント集
```

## 構成

```
.claude/skills/topic/
  SKILL.md                 -- スキル本体（処理手順・判定ロジック）
  quality-guidelines.md    -- 執筆品質ガイドライン
  template-problem.md      -- 課題解決型テンプレート
  template-project.md      -- プロジェクト紹介型テンプレート
  template-tips.md         -- ノウハウ型テンプレート

.tmp/
  zenn-drafts/             -- Zenn 記事ドラフト（gitignore）
  (将来: note-drafts/ 等)  -- プラットフォーム別に追加
```

## 出力

生成された記事はプラットフォーム別のフォルダに保存される（git 管理外）。

- Zenn: `.tmp/zenn-drafts/`
- 記事化履歴: `.tmp/zenn-drafts/published.txt`
