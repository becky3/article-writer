# article-writer

開発知見から技術記事を生成するツール。

## プロジェクト概要

- `/topic` スキルで記事を生成する Claude Code スキルプロジェクト
- 現在は Zenn 形式に対応。note 等への拡張を予定
- 記事ドラフトは `.tmp/drafts/` に出力（git 管理外）

## Git 運用

- `main` ブランチのみ（シンプル運用）
- コミット: `type(scope): 説明`
