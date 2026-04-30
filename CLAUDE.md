# article-writer

開発知見から技術記事を生成するツール。

## プロジェクト概要

- プラットフォーム別スキルで記事を生成する Claude Code スキルプロジェクト
- 現在は Zenn 形式に対応（`/write-zenn`）
- 生成記事は `articles/{platform}/{YYYYMMDD-HHMMSS}-{slug}.md`（git 管理下）に出力
- 素材源として参照する対象リポジトリは `.claude/sources.yml` で管理。ローカルパス解決には環境変数 `LOCAL_REPOS_ROOT` を使用

## Git 運用

- `main` ブランチのみ（シンプル運用）
- コミット: `type(scope): 説明`
