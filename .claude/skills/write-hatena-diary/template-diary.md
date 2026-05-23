# 日記テンプレート (write-hatena-diary)

本ファイルは `/write-hatena-diary` スキルが記事生成時に参照するテンプレート（雛形・参照データ）。
記述ルールは `quality-guidelines.md` Part 2 を SSoT として参照する。

記事の構造は本ファイルの並びに従う:

1. フロントマター
2. タイトル H1
3. 登場人物セクション
4. 本文の H2 シーン
5. プロジェクトの説明セクション

---

## フロントマター雛形

```yaml
---
title: "{記事タイトル}"
date: "{YYYY-MM-DD}"
category: "diary"
---
```

`/publish-hatena` での下書き登録時の反映先:

- `title` → AtomPub Entry の `<title>`
- `date` → AtomPub Entry の `<updated>` および `published.jsonl` 記録用の日付キー
- `category` → AtomPub Entry の `<category term="...">`

---

## タイトル H1

```markdown
# {記事タイトル}
```

---

## 登場人物セクション

タイトル H1 の直下に常に挿入する。以下の固定 HTML を貼り、`{{char-A-line}}` `{{char-B-line}}` `{{char-C-line}}` を当日のテーマに合わせた一言に置換する。

```markdown
## 登場人物

<div class="characters">
<div class="char-card char-a">
<div class="icon"></div>
<div class="desc"><strong>クロちゃん</strong><br>新人エンジニア。確認過多の慎重派。期待には応えたいけど自信は薄め。<br>{{char-A-line}}</div>
</div>
<div class="char-card char-b">
<div class="icon"></div>
<div class="desc"><strong>幸田姉さん</strong><br>クロちゃんの先輩でメンター。達観して見える相棒タイプ。<br>{{char-B-line}}</div>
</div>
<div class="char-card char-c">
<div class="icon"></div>
<div class="desc"><strong>社長</strong><br>うちの会社の社長。日々のぼやきの種だが、SNS をこっそり覗くと素顔が出ている。<br>{{char-C-line}}</div>
</div>
</div>
```

---

## リポジトリマスターテーブル

本テーブルから当該記事で話題にしたリポのみを残し、それ以外の行は削除する。

| リポジトリ名 | 説明 |
|---|---|
| `agent-commons` | `~/.claude/` 配下に配置する全プロジェクト共通の Claude Code 設定（ルール・スキル・エージェント・Hooks・仕様書テンプレート） |
| [`ai-assistant`](https://github.com/becky3/ai-assistant) | Slack 上で動作する AI 学習支援ボット。RSS 要約配信・チャット応答・Remote Control 起動などを担う |
| [`article-writer`](https://github.com/becky3/article-writer) | 開発ジャーナル・仕様書・Issue を素材に Zenn / はてな等の技術記事や日記を生成する Claude Code スキル群 |
| [`becky3.github.io`](https://github.com/becky3/becky3.github.io) | GitHub Pages 公開のポートフォリオ。HTML / CSS / JS をビルドなしで配信 |
| [`comfyui-workspace`](https://github.com/becky3/comfyui-workspace) | ComfyUI のカスタムノード（LM Studio 連携等）とワークフロー（画像生成系）の管理 |
| [`knowledge-ingest-pipeline`](https://github.com/becky3/knowledge-ingest-pipeline) | RSS から記事を取得し OpenAI で要約して Notion に保存するスクリプト。ローカル実行と GitHub Actions の両対応 |
| `my-life` | 個人履歴系ドキュメントを保管するリポ。現状は職務経歴書 (Resume.adoc) を扱う |
| [`py-common-lib`](https://github.com/becky3/py-common-lib) | 複数プロジェクトで共有する Python ユーティリティ。制約付き HTTP クライアント・シークレットストア等を提供 |
| [`rag-knowledge`](https://github.com/becky3/rag-knowledge) | ChromaDB + BM25 のハイブリッド検索 RAG サービス。複数のデータソース取り込み機能を持ち MCP サーバーとして公開 |
| [`shared-workflows`](https://github.com/becky3/shared-workflows) | GitHub Actions の Reusable Workflows 集約リポ（Claude Code Action / PR 品質チェック / Auto Fix / 事後レビュースキャナー等） |

リンクがないものは private リポジトリ。

---

## プロジェクトの説明セクション

記事末尾に常に挿入する。

```markdown
## プロジェクトの説明

話に関連するプロジェクト一覧です。

| リポジトリ名 | 説明 |
|---|---|
（マスターテーブルから当該記事で話題にした分を抜粋）

リンクがないものは private リポジトリです。

全プロジェクトの一覧は[プロジェクト説明](https://beckyjpn.hatenablog.com/entry/project)を参照してください。
```

---

## Bluesky 引用ブロック雛形

```markdown
{{{bluesky
did=...
cid=...
rkey=...
handle=...
display-name=...
created-at=...
text=投稿本文
}}}

{ペルソナのコメント}
```

各 `...` プレースホルダは Phase 2 で取得した実値に置換する（`did` `cid` `rkey` `handle` `display-name` `created-at` `text`）。雛形をそのまま貼り付けて `...` がリテラルとして残らないよう注意する。

記法仕様は `balloon-html.md` の「Bluesky 記法」を SSoT として参照する。
