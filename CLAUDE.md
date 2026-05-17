# article-writer

開発知見から技術記事を生成するツール。

## プロジェクト概要

- プラットフォーム別スキルで記事を生成する Claude Code スキルプロジェクト
- 記事生成スキル: `/write-zenn`（Zenn 形式）/ `/write-hatena-diary`（はてなブログ向け日記）
- 記事投稿スキル: `/publish-hatena`（はてなブログ AtomPub で下書き登録）
- 記事レビュースキル: `/multi-perspective-review`（観点別エージェント並列レビュー、生成後の品質確認用）
- 生成記事は `articles/{platform}/` 配下に出力（ファイル名規約は各スキル SKILL.md を参照）
- 素材源として参照する対象リポジトリは `.claude/sources.yml` で管理。ローカルパス解決には環境変数 `LOCAL_REPOS_ROOT` を使用

## Git 運用

- 常設ブランチは `main` のみ（`develop` なし、シンプル運用）
- 作業ブランチ: `feature/{機能名}-#{Issue番号}` を切って PR 経由で `main` へマージ
- コミット: `type(scope): 説明 (#Issue番号)`

## 作業フロー

記事執筆と、執筆中のフィードバックをスキル/ルール側に還元する作業フローは [docs/workflows/article-writing-workflow.md](docs/workflows/article-writing-workflow.md) を参照。

## /auto-finalize 利用時の注意

`/auto-finalize`（agent-commons 側スキル）は **ステップ 4「計画整合性照合」** で計画ファイル `aidlc-docs/plan-work/issue-<番号>.md` ↔ diff の機械的整合チェックを行う。本リポジトリでの運用方針は以下の通り。

- **`/start-work` 未経由** の場合（記事ワークを含む）: 計画ファイルは存在しないため、ステップ 4 の `/plan-work` レーン整合チェックはスキップしてよい。`/auto-finalize` はそのまま push + PR 作成 + 監視ループ起動まで進める
- **`/start-work` 経由（`/plan-work` または `/aidlc`）**: 従来通り計画整合性照合を通す

実現手段: agent-commons 側 `/auto-finalize` のステップ 4.0 は「`/plan-work` レーンで計画ファイル不在ならエラー停止」する仕様。
本リポジトリの `/start-work` 未経由作業では Claude がそのエラー停止を検出した時点で本セクションを根拠にステップ 4 をスキップし、ステップ 5（認可フラグ作成）以降に進める。
`/auto-finalize` のスキル本体は agent-commons 側の SSoT であり、本リポジトリ側で修正対象としない。

## エディタ自動オープン方針

- `/write-hatena-diary`: 生成記事を自動オープン（ユーザー確認動線として）
- `/review-hatena-diary`: 集約ファイルを自動オープンしない（チャット表示で完結）
- 記事は内容確認が必須、レビュー結果はチャット要約で十分という棲み分け

## ルール

リポジトリ固有のルール（編集時の Edit 強制等）は [.claude/rules/conventions.md](.claude/rules/conventions.md) を参照。
