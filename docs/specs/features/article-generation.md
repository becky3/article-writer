# 技術記事生成

## 概要

開発知見（ジャーナル / GitHub Issue / 仕様書 / コード）を素材として、技術記事ドラフトを Claude Code スキル経由で生成する機能。

プラットフォームごとに独立したスキルを提供する。

Zenn 向け技術記事は `/write-zenn`、はてなブログ向け日記は `/write-hatena-diary` を提供する。

生成後の品質確認用として、Zenn 記事には観点別エージェント並列レビュー `/multi-perspective-review`、日記記事には日記特化の `/review-hatena-diary` を提供する。

日記側では `/write-hatena-diary` が生成直後に `/review-hatena-diary` を自動呼び出しし、レビュー指摘の確認・修正適用までを統合実行する。

## 背景

開発の中で得られた学び・判断・気づきは、ジャーナルやドキュメントに散在する。これらを技術記事として外部に公開するには、素材の収集・記事タイプの判断・プラットフォーム固有のフォーマット適用といった作業が必要になる。本機能は、これらを Claude Code スキルとして自動化し、執筆者がレビュー・調整に集中できるようにする。

プラットフォームごとに必要なフロントマター・記法・トーンが異なるため、共通レイヤーで抽象化するのではなく、プラットフォーム別の独立スキルとして実装する方針を採る。スキル間でロジックが重複しても、各プラットフォームの特性に合わせた表現を独立に最適化できるメリットを優先する。

## 制約

- 生成される記事ドラフトは `published: false` 等のプラットフォーム既定の非公開状態とする。公開判断は人間が行う
- 生成された記事は必ずレビューしてから公開する（事実確認・推敲・正直さの観点）
- 出力先は `articles/{platform}/{YYYYMMDD-HHMMSS}-{article-slug}.md` とし、git 管理下に置く（記事の経緯と差分を git で追跡可能にする）
- `{platform}` の命名はスキル名 `/write-{platform}` の `{platform}` 部分と一致させる。SSoT は各スキル SKILL.md
- 著作物・実在する個人/作品由来の固有名詞・特徴的言い回しを記事本文に混入しない（`~/.claude/rules/invariants.md` 準拠）
- 素材源として参照する対象リポジトリは `.claude/sources.yml` で一元管理する。各リポのローカルパスは環境変数 `LOCAL_REPOS_ROOT` を起点に `${LOCAL_REPOS_ROOT}/<owner>/<name>` で解決する
- トピック候補化（Phase A）はリポジトリ単位のサブエージェント（`repo-scanner`）を並列起動して候補を集約する。対象リポは「固定 3 リポ + ランダム 3 リポ」の合計 6 リポを毎回選定する（活動量の多いリポを継続的にカバーしつつ、他リポも探索対象に含める意図）

## 操作一覧

| 操作 | トリガー | 概要 |
|---|---|---|
| `/write-zenn` | Claude Code セッション内のスラッシュコマンド | Zenn 形式の技術記事ドラフトを生成する |
| `/write-hatena-diary` | Claude Code セッション内のスラッシュコマンド | はてなブログ向け日記記事を生成する。生成直後に `/review-hatena-diary` を自動呼び出しする |
| `/multi-perspective-review` | Claude Code セッション内のスラッシュコマンド | Zenn 記事 markdown を観点別エージェントで並列レビューする（公開前の最終確認用、任意起動） |
| `/review-hatena-diary` | Claude Code セッション内のスラッシュコマンド（自動 / 手動） | はてなブログ向け日記記事を 3 観点（キャラ整合性 / ガイドライン準拠 / 言及正確性）で並列レビューし、指摘を triage 経由で確認・修正適用する。`/write-hatena-diary` から自動呼び出しされる |

## 各操作の仕様

### `/write-zenn`

Zenn 形式の技術記事ドラフトを生成するスキル。

- **トリガー**: Claude Code セッション内で `/write-zenn` をスラッシュコマンドとして実行
- **入力**: 引数なし（トピック候補から選択）または `<テーマ>`（自由文での直接指定）
- **素材**: `.claude/sources.yml` に記載された対象リポジトリ群を横断する。素材源はジャーナル（RAG 経由）・GitHub Issue（`gh` CLI）・各リポの `docs/specs/` 配下・関連コード
- **出力**: `articles/zenn/{YYYYMMDD-HHMMSS}-{article-slug}.md`
- **公開後の追記**: 記事公開後にユーザー指示を受けたタイミングで、`articles/zenn/published.txt` に記事化履歴を追記する
- **動作仕様の詳細**（処理手順・記事タイプ判定ロジック・テンプレート・品質ガイドライン）: `.claude/skills/write-zenn/SKILL.md` および同階層の関連ファイルに保持する

### `/write-hatena-diary`

はてなブログ向け日記記事を生成するスキル。

- **トリガー**: Claude Code セッション内で `/write-hatena-diary [日付指定]` をスラッシュコマンドとして実行
- **入力**: 引数なし（実行日）または `<YYYY-MM-DD>` / `<MM-DD>` / `<日付>..<日付>`（範囲指定）。範囲指定はジャーナル存在日ごとに 1 記事ずつ生成する
- **素材**: 指定日のジャーナル（必須・RAG 経由）と Bluesky 投稿（任意）
- **出力**: `articles/hatena/{YYYY-MM-DD}-{HH-MM-SS}-{article-slug}.md`
- **生成直後の自動レビュー**: 各記事を Write した直後に `/review-hatena-diary` を自動呼び出しし、3 観点並列レビュー → triage 連携 → 修正適用 までを当該記事のループ内で完結させる
- **投稿（別スキル）**: はてなブログへの下書き登録は `/publish-hatena` スキルで行う
- **動作仕様の詳細**（Phase 構成・素材取得・記法ポリシー・記事構成）: `.claude/skills/write-hatena-diary/SKILL.md` および同階層の関連ファイル（`quality-guidelines.md` / `narrative-guidelines.md` / `template-diary.md` / `balloon-html.md`）に保持する

### `/multi-perspective-review`

Zenn 記事 markdown を観点別エージェントで並列レビューするスキル。

- **トリガー**: Claude Code セッション内で `/multi-perspective-review <対象ファイルパス> [観点1,観点2,...]` をスラッシュコマンドとして実行
- **入力**: 必須引数として記事 markdown ファイルパス。任意引数として観点リスト（カンマ区切り）。観点を省略するとデフォルト 5 観点（構成・主題整合性 / 冗長性・重複 / 読者視点 / 文体一貫性 / ガイドライン準拠チェック）で並列起動する
- **対象**: Zenn 記事 markdown を主想定（`articles/zenn/*.md`）。日記記事（`articles/hatena/*.md`）には日記特化の `/review-hatena-diary` を使うこと
- **起動タイミング**: 記事生成完了後・公開前の最終確認用、任意起動。`/write-zenn` からの自動呼び出しはしない
- **出力**: `.tmp/multi-perspective-review/{YYYYMMDD-HHMMSS}-{slug}.md`（観点別の指摘集約レポート）。出力後 `code` コマンドで自動オープン
- **動作仕様の詳細**（観点定義・サブエージェント並列起動手順・出力フォーマット）: `.claude/skills/multi-perspective-review/SKILL.md` に保持する

### `/review-hatena-diary`

はてなブログ向け日記記事を日記特化の 3 観点で並列レビューするスキル。

- **トリガー**: `/write-hatena-diary` から自動呼び出し、または Claude Code セッション内で `/review-hatena-diary <対象ファイルパス>` を手動起動
- **入力**: 必須引数として対象記事ファイルパス（リポルートからの相対パス）
- **対象**: 日記記事 markdown 専用（`articles/hatena/*.md`）
- **観点**: 3 観点固定（観点引数による絞り込みなし）
  - キャラ整合性（一人称・複数形・口調・キャラ取り違え）
  - ガイドライン準拠（`quality-guidelines.md` 全節の機械照合 + 著作物・IP 検出）
  - 言及正確性（リポ名・スキル名・事実関係の素材ジャーナル照合）
- **処理**: 3 観点を `general-purpose` サブエージェントで並列起動 → 結果集約 → `/triage` 連携で指摘を確認 → 確定した修正方針を対象記事へ Edit で適用
- **出力**: `.tmp/review-hatena-diary/{YYYYMMDD-HHMMSS}-{slug}.md`（観点別の指摘集約レポート）。出力後 `code` コマンドで自動オープン
- **動作仕様の詳細**（観点定義・サブエージェント並列起動手順・triage 連携・修正適用フロー）: `.claude/skills/review-hatena-diary/SKILL.md` に保持する

## コンポーネント構成

```mermaid
flowchart LR
    User[ユーザー] -->|/write-zenn| ZennSkill[write-zenn スキル]
    Sources[.claude/sources.yml<br/>対象リポジトリ群] --> ZennSkill
    ZennSkill -->|Phase A 候補化<br/>6 リポ並列起動| Scanner[repo-scanner<br/>サブエージェント x 6]
    Scanner -->|Issue 走査| GH[(GitHub<br/>gh CLI)]
    Scanner -->|関連ジャーナル検索| RAG[(rag-knowledge-production<br/>MCP)]
    Scanner -->|候補返却| ZennSkill
    ZennSkill -->|Phase B 素材取得| RAG
    ZennSkill -->|Phase B 素材取得| GH
    ZennSkill -->|Phase B 素材取得| Local[ローカルファイル<br/>各リポの docs/specs 等]
    ZennSkill -->|生成| ZennArticle[articles/zenn/<br/>記事ファイル<br/>git 管理下]
    ZennArticle -->|手動レビュー推奨| ZennReview[multi-perspective-review<br/>5 観点並列]
    ZennArticle -->|人手レビュー| ZennPublish[Zenn 公開]

    User -->|/write-hatena-diary| DiarySkill[write-hatena-diary スキル]
    DiarySkill -->|素材取得| RAG
    DiarySkill -->|生成| DiaryArticle[articles/hatena/<br/>日記記事<br/>git 管理下]
    DiaryArticle -->|Phase 5.5 で自動呼び出し| DiaryReview[review-hatena-diary<br/>3 観点並列]
    DiaryReview -->|指摘の triage 連携| Triage[/triage スキル]
    Triage -->|確定修正の適用| DiaryArticle
    DiaryArticle -->|/publish-hatena| HatenaPublish[はてなブログ<br/>下書き登録]
```

## 関連ドキュメント

- `.claude/skills/write-zenn/SKILL.md`: `/write-zenn` スキル本体（動作仕様）
- `.claude/skills/write-zenn/quality-guidelines.md`: 執筆品質ガイドライン（`/multi-perspective-review` のガイドライン準拠チェック観点もこれを参照する）
- `.claude/skills/write-zenn/template-*.md`: 記事タイプ別テンプレート
- `.claude/skills/write-hatena-diary/SKILL.md`: `/write-hatena-diary` スキル本体（動作仕様）
- `.claude/skills/write-hatena-diary/quality-guidelines.md`: 日記の品質ガイド（恒久ルール、`/review-hatena-diary` 観点 2「ガイドライン準拠」が参照）
- `.claude/skills/write-hatena-diary/narrative-guidelines.md`: 日記の物語ガイド（書き手ペルソナ・キャラクター・関係性、`/review-hatena-diary` 観点 1「キャラ整合性」が参照）
- `.claude/skills/write-hatena-diary/template-diary.md`: 日記テンプレート・記法ポリシー・リポジトリマスターテーブル
- `.claude/skills/write-hatena-diary/balloon-html.md`: 吹き出し・Bluesky 埋め込みの簡素記法仕様
- `.claude/skills/multi-perspective-review/SKILL.md`: `/multi-perspective-review` スキル本体（Zenn 向け観点別並列レビュー）
- `.claude/skills/review-hatena-diary/SKILL.md`: `/review-hatena-diary` スキル本体（日記向け 3 観点並列レビュー + triage 連携）
- `.claude/agents/repo-scanner.md`: Phase A の候補抽出を担当するサブエージェント定義
- `.claude/sources.yml`: 素材源として参照する対象リポジトリ一覧
