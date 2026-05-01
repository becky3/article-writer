# article-writer

開発知見から技術記事を生成するツール。

## プロジェクト概要

- プラットフォーム別スキルで記事を生成する Claude Code スキルプロジェクト
- 現在は Zenn 形式に対応（`/write-zenn`）
- 生成記事は `articles/{platform}/{YYYYMMDD-HHMMSS}-{article-slug}.md`（git 管理下）に出力
- 素材源として参照する対象リポジトリは `.claude/sources.yml` で管理。ローカルパス解決には環境変数 `LOCAL_REPOS_ROOT` を使用

## Git 運用

- 常設ブランチは `main` のみ（`develop` なし、シンプル運用）
- 作業ブランチ: `feature/{機能名}-#{Issue番号}` を切って PR 経由で `main` へマージ
- コミット: `type(scope): 説明 (#Issue番号)`

## 作業フロー

記事執筆と、執筆中のフィードバックをスキル/ルール側に還元する作業フローは [docs/workflows/article-writing-workflow.md](docs/workflows/article-writing-workflow.md) を参照。
