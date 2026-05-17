# 日記テンプレート (write-hatena-diary)

本ファイルは `/write-hatena-diary` スキルが記事生成時に参照するテンプレート。
生成記事の本文と末尾「プロジェクトの説明」セクションを組み立てる。

## 記法ポリシー

本スキルは **GitHub-flavored Markdown（GFM）のみ** で記事を生成する。はてな記法（`[id:foo:title]` 形式、`>>>` 引用、`*` や `**` の独自意味付け等）は使用しない。Markdown と競合する記号（文字としての `_` など）は `\_` のようにバックスラッシュエスケープする。

**絵文字は Unicode 直接記述** を使う（例: ✨ 🙏 📝 ✍️ 🌱 🎉）。GFM ショートコード形式（`:sparkles:` `:pray:` `:memo:` 等）は **使わない**。はてなブログ Markdown モードはショートコードをレンダリングせず、そのまま `:sparkles:` という文字列として記事に表示されてしまう。

運用前提として、はてなブログ側のデフォルト編集モードを「Markdown」に設定しておく必要がある（「設定 → 基本設定 → 編集モード → Markdown」）。記事作成後に編集モードを変更できないため、本前提を満たさないと意図したフォーマットで表示されない。本前提はユーザー手動運用の範囲とし、スキルでは検知しない。

吹き出し・Bluesky 埋め込みの記法仕様は `balloon-html.md` を参照（簡素記法ブロック内のインラインコード扱い・本文に書ける要素・エラー条件等の詳細を記載）。

なお、**生成記事 (`articles/hatena/**`) はリポジトリの markdownlint 対象外** としている（フロントマター + H1 重複 / HTML 埋め込み / 日本語段落の line-length 超過が頻発し、機械的 lint の便益が低いため）。

---

## リポジトリマスターテーブル

**記事本文での `name` 表記**: ジャーナルに登場するリポ名（GitHub `becky3/<name>` の `<name>` 部分）を `` `<name>` `` の backtick 付き形式で本文に書く（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式や Issue / PR 番号は本文に書かない。

「プロジェクトの説明セクション」では、本テーブルから **素材ジャーナル本文にリポ名が明示されているリポのみ** を残し、それ以外の行は削除する（機能描写のみで該当扱いにはしない）。

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
| [`rag-knowledge`](https://github.com/becky3/rag-knowledge) | ChromaDB + BM25 のハイブリッド検索 RAG サービス。Web / Bluesky / YouTube / Zenn / Journal の各インジェスタを持ち MCP サーバーとして公開 |
| [`shared-workflows`](https://github.com/becky3/shared-workflows) | GitHub Actions の Reusable Workflows 集約リポ（Claude Code Action / PR 品質チェック / Auto Fix / 事後レビュースキャナー等） |

リンクがないものは private リポジトリ。

---

## 記事フロントマター雛形

```yaml
---
title: "{記事タイトル}"
date: "{YYYY-MM-DD}"
category: "diary"
---
```

`title` / `date` / `category` の 3 項目のみ。`/publish-hatena` での下書き登録時に、これらの値が以下のように反映される:

- `title` → AtomPub Entry の `<title>`
- `date` → AtomPub Entry の `<updated>`（JST 0 時として ISO 8601 化、はてなブログ管理画面の公開予定日として表示）および `published.jsonl` 記録用の日付キー
- `category` → AtomPub Entry の `<category term="...">`

---

## 記事の機械的出版要件

本セクションは記事生成時の **機械的に守るべき要件のみ** を定める。本文の構成・口調・セクション分けは `quality-guidelines.md` Part 1（物語世界）を制御点として、書き手の裁量に任せる。

### タイトル

```markdown
# {記事タイトル}
```

- フロントマター `title:` と本文先頭 H1 のタイトル文字列は一致させる
- タイトル文字列の決め方（内容・字数・調子）は `quality-guidelines.md` 「タイトル」セクションを SSoT として参照

### リポジトリ言及

- 本文中でリポジトリに言及する場合は、`name` を backtick 付きで直接書く
- `becky3/<name>` 形式・GitHub URL・Issue / PR 番号は本文に書かない
- リポの個別説明は本文中に書かない（プロジェクトの説明セクションのテーブルで掲載）

### セクション配置の順序

- 記事は以下の順で構成する
  1. タイトル H1
  2. `## 登場人物` — 登場人物セクション（タイトル H1 直下、3 カードの固定 HTML）
  3. 本文の H2 シーン（複数）
  4. `## プロジェクトの説明` — 末尾。話に関連するリポジトリ一覧（テーブル）と全プロジェクト一覧へのリンク

### 登場人物セクション

- 配置: タイトル H1 の直下（最初の H2 セクション）
- 言及リポ・対話シーン数に関わらず常に挿入する
- 3 カード（クロちゃん／幸田姉さん／社長）を `hatena-design.css` の `.characters` / `.char-card.char-a/b/c` クラスで並べる
- 構造は固定 HTML 文言とし、書き手は改変しない

#### 固定 HTML（このまま記事に貼る）

事実情報（名前・属性・特徴）は **完全固定文言**。当日のテーマに合わせた一言部分だけ `{{char-A-line}}` / `{{char-B-line}}` / `{{char-C-line}}` のマーカーを置換する:

```markdown
## 登場人物

<div class="characters">
<div class="char-card char-a">
<div class="icon"></div>
<div class="desc"><strong>クロちゃん</strong>（新人・24 歳）<br>確認過多の慎重派。期待には応えたいけど自信は薄め。<br>{{char-A-line}}</div>
</div>
<div class="char-card char-b">
<div class="icon"></div>
<div class="desc"><strong>幸田姉さん</strong>（先輩・36 歳）<br>達観して見える相棒タイプ。クロちゃんの先輩。<br>{{char-B-line}}</div>
</div>
<div class="char-card char-c">
<div class="icon"></div>
<div class="desc"><strong>社長</strong><br>うちの会社の社長。日々のぼやきの種だが、SNS をこっそり覗くと素顔が出ている。<br>{{char-C-line}}</div>
</div>
</div>
```

#### マーカーの置換ルール

- `{{char-A-line}}` / `{{char-B-line}}` / `{{char-C-line}}` の 3 マーカーは **必ずすべて置換する**（マーカーが記事に残るのは禁止）
- 一言の方針（字数・トーン・書き方）は `quality-guidelines.md` Part 1「登場人物」「登場人物セクションの一言」を SSoT として参照する
- 事実情報部分（`<strong>名前</strong>` 〜 `<br>` 直前まで）は **書き手が改変しない**。ぶれ防止のため固定文言で運用する

### プロジェクトの説明セクション

- 配置: 記事末尾（本文の最後の H2 シーンの後ろ）
- 言及リポの有無に関わらず常に挿入する
- 上記「リポジトリマスターテーブル」冒頭の説明（素材ジャーナル本文に明示的に登場するリポのみを残す）に従って行を絞り込む
- 末尾に[プロジェクト説明](https://beckyjpn.hatenablog.com/entry/project)（全プロジェクト一覧）へのリンクを添える

セクション本体:

```markdown
## プロジェクトの説明

話に関連するプロジェクト一覧です。

| リポジトリ名 | 説明 |
|---|---|
（マスターテーブルから話に関連する分を抜粋）

リンクがないものは private リポジトリです。

全プロジェクトの一覧は[プロジェクト説明](https://beckyjpn.hatenablog.com/entry/project)を参照してください。
```

---

## Bluesky 引用フォーマット

- Bluesky 投稿は `:::bluesky` 簡素記法で記事本文に直接書く
- 変換は `/publish-hatena` 投稿時に `scripts/convert_article_html.py` が実施（HTML 埋め込みカードに展開）
- 記法仕様（キー一覧・複数行 text の扱い・必須キー）は `balloon-html.md` の「Bluesky 記法」を SSoT として参照する
- `articles/hatena/*.md` には簡素記法のまま保存し、HTML 展開済みのスニペットは書かない
- 1 投稿 = 1 ブロック。複数投稿があればブロックを繰り返す
- 各投稿ブロックの直後にペルソナのコメントを書く（コメントの内容・トーンは `quality-guidelines.md` Part 1「登場人物」を参照）
- ブロック内に DID / handle / 投稿日時が含まれるため、本文中で別途これらを書き出す必要はない

書式例:

```markdown
:::bluesky
did=...
cid=...
rkey=...
handle=...
display-name=...
created-at=...
text=投稿本文
:::

{ペルソナのコメント}
```
