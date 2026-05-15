# 日記テンプレート (write-hatena-diary)

本ファイルは `/write-hatena-diary` スキルが記事生成時に参照するテンプレート。
生成記事の本文と末尾「プロジェクトの説明」セクションを組み立てる。

## 記法ポリシー

本スキルは **GitHub-flavored Markdown（GFM）のみ** で記事を生成する。はてな記法（`[id:foo:title]` 形式、`>>>` 引用、`*` や `**` の独自意味付け等）は使用しない。Markdown と競合する記号（文字としての `_` など）は `\_` のようにバックスラッシュエスケープする。

**絵文字は Unicode 直接記述** を使う（例: ✨ 🙏 📝 ✍️ 🌱 🎉）。GFM ショートコード形式（`:sparkles:` `:pray:` `:memo:` 等）は **使わない**。はてなブログ Markdown モードはショートコードをレンダリングせず、そのまま `:sparkles:` という文字列として記事に表示されてしまう。

運用前提として、はてなブログ側のデフォルト編集モードを「Markdown」に設定しておく必要がある（「設定 → 基本設定 → 編集モード → Markdown」）。記事作成後に編集モードを変更できないため、本前提を満たさないと意図したフォーマットで表示されない。本前提はユーザー手動運用の範囲とし、スキルでは検知しない。

**HTML タグ内では Markdown 構文が解釈されない**。
`<div>` `<span>` 等のブロック内に書いた `` ` `` `*` `**` 等は文字列として表示される。
リポ名・スキル名・コード断片など本来 `` ` `` で囲みたい箇所は、HTML タグ内では `<code>` タグを使う（例: `<div class="text">「<code>agent-commons</code> のルール改修をしてて」</div>`）。
Markdown 構文が使えるのは HTML タグの外（通常の段落・H2/H3 見出し等）のみ。

なお、**生成記事 (`articles/hatena/**`) はリポジトリの markdownlint 対象外** としている（フロントマター + H1 重複 / HTML 埋め込み / 日本語段落の line-length 超過が頻発し、機械的 lint の便益が低いため）。

---

## リポジトリマスターテーブル

リポジトリの個別説明（実態説明 + 参照 URL）は外部記事 <https://beckyjpn.hatenablog.com/entry/project> を SSoT とする。

**記事本文での `name` 表記**: ジャーナルに登場するリポ名（GitHub `becky3/<name>` の `<name>` 部分）を `` `<name>` `` の backtick 付き形式で本文に書く（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式や Issue / PR 番号は本文に書かない。

| name | visibility |
|---|---|
| agent-commons | private |
| ai-assistant | public |
| article-writer | public |
| becky3.github.io | public |
| comfyui-workspace | public |
| knowledge-ingest-pipeline | public |
| my-life | private |
| py-common-lib | public |
| rag-knowledge | public |
| shared-workflows | public |

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
- `date` → AtomPub Entry の `<updated>`（JST 0 時として ISO 8601 化、はてなブログ管理画面の公開予定日として表示）および `published.txt` 記録用の日付キー
- `category` → AtomPub Entry の `<category term="...">`

---

## 記事の機械的出版要件

本セクションは記事生成時の **機械的に守るべき要件のみ** を定める。本文の構成・口調・トーン・セクション分けは `persona.md` を制御点として、書き手の裁量に任せる。

### タイトル

```markdown
# {記事タイトル}
```

- フロントマター `title:` と本文先頭 H1 のタイトル文字列は一致させる
- タイトル文字列の決め方（内容・字数・調子）は `quality-guidelines.md` 「タイトル」セクションを SSoT として参照

### リポジトリ言及

本文中でリポジトリに言及する場合は、`name` を backtick 付きで直接書く（例: `` `rag-knowledge` `` 、 `` `article-writer` `` ）。
`becky3/<name>` 形式・GitHub URL・Issue / PR 番号は本文に書かない（個別説明は冒頭固定セクションの外部記事に集約済）。

### 冒頭固定セクション

記事冒頭（タイトル直下のリード文）で以下を **固定文言で常に挿入する**（言及リポの有無に関わらず）:

```markdown
## プロジェクトの説明

リポジトリ名などの説明は以下を参照ください。

[プロジェクト説明](https://beckyjpn.hatenablog.com/entry/project)
```

リポごとの実態説明・visibility 表記・GitHub URL は外部記事側で管理する。

---

## Bluesky 引用フォーマット

Bluesky 投稿は、はてなブログ Markdown モードでもプレビュー時点で投稿カードとして表示されるよう、**`scripts/generate_bluesky_embed.py` で生成した HTML 埋め込みスニペット** を Markdown 本文に直接挿入する。

スニペットの生成は SKILL.md Phase 4 で行う（投稿ごとに以下のコマンドを実行し、stdout の HTML を取得）:

```bash
python scripts/generate_bluesky_embed.py \
  --did <DID> \
  --cid <CID> \
  --rkey <rkey> \
  --handle <handle> \
  --display-name <表示名> \
  --text "<投稿本文>" \
  --created-at <ISO 8601> \
  [--lang ja]
```

各投稿の HTML スニペットを記事本文に挿入し、その直後の段落にペルソナのコメントを書く:

```markdown
{HTML スニペット（複数行）}

{ペルソナのコメント。エンタメ寄りトーン。1〜2 段落}
```

引用は 1 投稿 = 1 スニペット。複数投稿があればスニペットとコメントを繰り返す。スニペット内に DID / handle / 投稿日時が含まれるため、本文中で別途これらを書き出す必要はない。
