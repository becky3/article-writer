# 日記テンプレート (write-hatena-diary)

本ファイルは `/write-hatena-diary` スキルが記事生成時に参照するテンプレート（雛形・参照データ）。
記述ルールは `quality-guidelines.md`（恒久ルール）と `narrative-guidelines.md`（物語世界）を SSoT として参照する。

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
pattern: "{進行パターン ID（`narrative-guidelines.md`「進行パターン」が SSoT）}"
---
```

`/publish-hatena` での下書き登録時の反映先:

- `title` → AtomPub Entry の `<title>`
- `date` → AtomPub Entry の `<updated>` および `published.jsonl` 記録用の日付キー
- `category` → AtomPub Entry の `<category term="...">`
- `pattern` → 進行パターン ID（`narrative-guidelines.md`「進行パターン」が SSoT）。AtomPub には送信せず、連続回避の参照と `published.jsonl` への転記に使う

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
<div class="desc"><strong>幸田姉さん</strong><br>クロちゃんの先輩でメンター。物言いはストレートだが、頼れる存在。<br>{{char-B-line}}</div>
</div>
<div class="char-card char-c">
<div class="icon"></div>
<div class="desc"><strong>社長</strong><br>うちの会社の社長。日々のぼやきの種だが、SNS をこっそり覗くと素顔が出ている。<br>{{char-C-line}}</div>
</div>
</div>
```

---

## プロジェクトの説明セクション

記事末尾に常に挿入する。

```markdown
## プロジェクトの説明

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
