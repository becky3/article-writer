# article-writer

開発ジャーナル・仕様書・Issue 等の開発知見から技術記事を生成する Claude Code スキル。

プラットフォームごとに独立したスキルを提供する。現在は Zenn 形式の記事生成スキル `/write-zenn` を提供する。生成後の品質確認用として、観点別エージェント並列レビューを行う `/multi-perspective-review` も併せて提供する。

## 機能

- ジャーナル（RAG 経由）・仕様書・Issue からトピック候補を自動抽出
- 記事タイプの自動判定（課題解決型 / プロジェクト紹介型 / ノウハウ型）
- テンプレートと品質ガイドラインに基づく記事生成
- 執筆品質チェック（markdownlint）
- 観点別エージェント並列レビュー（構成・主題整合性 / 冗長性・重複 / 読者視点 / 文体一貫性 / ガイドライン準拠チェックの 5 観点）

## 使い方

Claude Code セッション内で `/write-zenn` コマンドを実行する。

```text
# トピック候補を自動提案
/write-zenn

# テーマを直接指定して記事生成
/write-zenn Windows Git Bashでハマったポイント集
```

記事生成後、公開前の最終確認として `/multi-perspective-review` を任意で実行できる。

```text
# デフォルト 5 観点で並列レビュー
/multi-perspective-review articles/zenn/20260505-foo.md

# 観点を絞って実行（例: 文体と読者視点のみ）
/multi-perspective-review articles/zenn/20260505-foo.md 文体,読者視点
```

## 構成

```text
.claude/
  sources.yml              -- 素材源として参照する対象リポジトリ一覧
  skills/write-zenn/
    SKILL.md               -- スキル本体（処理手順・判定ロジック）
    quality-guidelines.md  -- 執筆品質ガイドライン
    template-problem.md    -- 課題解決型テンプレート
    template-project.md    -- プロジェクト紹介型テンプレート
    template-tips.md       -- ノウハウ型テンプレート

articles/
  zenn/                    -- Zenn 記事ファイル（git 管理下）
    YYYYMMDD-HHMMSS-{article-slug}.md
    published.txt          -- 記事化履歴
```

## 前提

`.claude/sources.yml` に列挙された各リポジトリのローカル配置を解決するため、環境変数 `LOCAL_REPOS_ROOT` を設定する必要がある。

例（リポジトリの親ディレクトリが `D:/GitHub` の場合）:

```text
LOCAL_REPOS_ROOT=D:/GitHub
```

各リポのローカルパスは `${LOCAL_REPOS_ROOT}/<owner>/<name>` として解決される。

## 出力

生成された記事は git 管理下の `articles/{platform}/` に保存される。

- Zenn: `articles/zenn/{YYYYMMDD-HHMMSS}-{article-slug}.md`
- 記事化履歴: `articles/zenn/published.txt`
