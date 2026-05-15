# 吹き出し / Bluesky 埋め込みの簡素記法

本ファイルは `/write-hatena-diary` が記事生成時に出力する吹き出し（balloon）と Bluesky 埋め込みの **簡素記法 → HTML 変換規約** を定める。
変換スクリプトは `scripts/convert_article_html.py`、起動は `/publish-hatena` 投稿時。

## 設計方針

- 生成スキルが書き出す `articles/hatena/*.md` は **簡素記法のまま** Git に保存する（HTML 直書きは禁止）
- 投稿時に `convert_article_html.py` が簡素記法を HTML に展開し、AtomPub の `<content>` にその HTML 入り Markdown を載せる
- 簡素記法ブロックは行頭から始まる `:::<種別>` 〜 `:::` のフェンス形式に統一
- ブロック内本文は **HTML 直書き**として扱う（Markdown 構文は解釈されない）。例外として `` `name` `` 形式のインラインコードのみ、変換スクリプトが `<code>name</code>` に自動置換する

## balloon 記法

### `:::l` — 左の話者（クロちゃん）

書き方:

```
:::l
ぼく、ちょっと相談があるんですが。
:::
```

展開後 HTML（1 行に圧縮される）:

```html
<div class="balloon balloon-l"><div class="icon"></div><div class="text">ぼく、ちょっと相談があるんですが。</div></div>
```

### `:::r` — 右の話者（幸田姉さん）

書き方:

```
:::r
あら、どうしたの。
:::
```

展開後 HTML:

```html
<div class="balloon balloon-r"><div class="icon"></div><div class="text">あら、どうしたの。</div></div>
```

### 本文に含められるもの

- 通常の文字列
- インラインコード `` `name` `` 形式（変換時に自動で `<code>name</code>` に置換される）
- `<code>...</code>` 等の HTML タグ（インライン要素、直書きも可）
- `<br>` による任意改行
- 複数行の本文（変換時は改行を半角スペースに置換した上で `<div class="text">` の中に入る）

含められないもの:

- 入れ子の `:::` ブロック
- ブロックレベル要素（`<p>` `<div>` 等）— 既存 `.text` div の中で破綻するため

## Bluesky 記法

### `:::bluesky` — Bluesky 投稿の埋め込み

書き方:

```
:::bluesky
did=did:plc:xxxxxxxxxxxxxxxxxxxxxxxx
cid=bafyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
rkey=3xxxxxxxxxxxx
handle=example.bsky.social
display-name=表示名
created-at=2026-05-14T01:33:34.400Z
lang=ja
text=投稿本文を 1 行で書く
:::
```

展開後 HTML（はてなブログ Markdown モードで投稿カードとして描画される）:

```html
<blockquote class="bluesky-embed" data-bluesky-uri="at://did:plc:xxx.../app.bsky.feed.post/3xxx..." data-bluesky-cid="bafyxxx...">
<p lang="ja">投稿本文を 1 行で書く</p>
— <a href="https://bsky.app/profile/did:plc:xxx...?ref_src=embed">表示名 (@example.bsky.social)</a> <a href="https://bsky.app/profile/did:plc:xxx.../post/3xxx...?ref_src=embed">2026-05-14T01:33:34.400Z</a></blockquote>
<p>
<script async="" src="https://embed.bsky.app/static/embed.js" charset="utf-8"></script>
<cite class="hatena-citation"><a href="https://bsky.app/profile/example.bsky.social/post/3xxx...">bsky.app</a></cite></p>
```

### キーと値

| キー | 必須 | 内容 |
|---|---|---|
| `did` | 必須 | 投稿者の DID。全角コロン `：` は半角 `:` に正規化される |
| `cid` | 必須 | 投稿の CID |
| `rkey` | 必須 | 投稿の rkey（URL 末尾の識別子） |
| `handle` | 必須 | 投稿者のハンドル（例: `user.bsky.social`） |
| `display-name` | 必須 | 投稿者の表示名 |
| `created-at` | 必須 | 投稿日時（ISO 8601） |
| `text` | 必須 | 投稿本文。改行を含めるときは `\n` 文字を埋めるのではなく、後述「複数行 text の扱い」に従う |
| `lang` | 任意 | 言語コード。省略時は `ja` |

### 複数行 text の扱い

Bluesky の投稿本文に改行が含まれる場合は、`text=` の値を **複数行に分けて書く**:

```
:::bluesky
did=did:plc:xxx
cid=bafyxxx
rkey=3xxx
handle=example.bsky.social
display-name=表示名
created-at=2026-05-14T01:33:34.400Z
text=1 行目
2 行目
3 行目
:::
```

`text=` で始まる行以降、閉じ `:::` までを `text` の値として連結する（改行をそのまま保持）。
そのため `text=` は **ブロック内の最後のキー** として配置すること。

すべての値は HTML エスケープされてから展開される（`<` `>` `&` `"` 等は安全な実体参照になる）。

## 非変換領域

簡素記法ブロックの外（地の文・H2 見出し・通常 Markdown 段落）はそのままパススルーされる。
balloon を使わない記事（例: イベント告知記事等）は変換スクリプトを通しても無変換で出力される。

## エラー条件

変換スクリプトが停止する条件:

| 条件 | 理由 |
|---|---|
| `:::l` / `:::r` / `:::bluesky` の閉じ `:::` がないままファイル末尾に到達 | 未閉鎖ブロック |
| `:::bluesky` ブロックで必須キーが欠落している | 埋め込み URL を組み立てられない |
| ブロック内に別のブロック開始（`:::l` 等）が現れた | 入れ子は未サポート |

## 書き手向けチェックリスト（生成 AI が踏みやすい落とし穴）

記事生成時に AI が繰り返し踏むパターン。簡素記法ブロックを書いた直後に以下を必ず自己チェックする。

### 1. H2 セクション境界での閉じ忘れ

H2 見出しの直前で最後の balloon を書くとき、書き手は「シーンが終わる」感覚で閉じ `:::` を書き忘れやすい。**H2 見出しは閉じの代わりにならない**。変換スクリプトは次のブロック開始まで balloon が続いていると解釈し、`入れ子は未サポート` エラーで停止する。

❌ 悪い例（閉じ忘れ）:

```
:::r
セリフ最終行...

## 次のシーン
```

✅ 良い例:

```
:::r
セリフ最終行...
:::

## 次のシーン
```

書いた直後の自己チェック手順: H2 見出しの直前 1〜3 行を見て、`:::` で閉じられているか目視確認する。

### 2. balloon 内に bluesky を入れ子で書かない

「セリフで投稿に言及する」流れで、つい balloon-l の中に bluesky ブロックを差し込みたくなるが、**入れ子は未サポート**。

❌ 悪い例（入れ子）:

```
:::l
姉さん、見てください。

:::bluesky
...
:::
:::
```

✅ 良い例（balloon を閉じてから bluesky）:

```
:::l
姉さん、見てください。
:::

:::bluesky
...
:::

:::r
あの人ね…
:::
```

書き手は「セリフ → 投稿 → セリフ」の流れを **3 つの独立したブロック** として並べる。投稿ブロックを balloon の中に入れない。

### 3. balloon 内のリポ名・コード断片は通常の backtick で書く

balloon ブロック内では HTML 直書きとして扱われるため Markdown 構文は素通しでは効かないが、**変換スクリプトが balloon 内の `` `name` `` を `<code>name</code>` に自動置換する**。書き手は balloon の **内外を問わず** 通常通り `` `agent-commons` `` の形で書ける。

✅ 良い例（balloon の内外で同じ書き方）:

```
:::l
`agent-commons` のルール書き直しが入りました。
:::

通常段落でも `agent-commons` と書ける。
```

`<code>...</code>` を直接書いてもよい（既に HTML 直書きとして通る）。ただし書き手が `<code>` と backtick を併用すると `` `<code>name</code>` `` のような二重囲みになり、表示時に backtick が文字として残るため、**併用は避ける**。通常は backtick だけで書けば十分。

### 自己チェックの順番

balloon / bluesky を含むシーンを書き終えるたびに、以下を実行する:

1. 各 H2 見出しの直前 1〜3 行を見て `:::` 閉じが揃っているか確認
2. balloon ブロック内に `:::bluesky` `:::l` `:::r` が混ざっていないか確認

2 つともクリアしてから次のシーンに進む。記事全体を書き終えてから一括チェックすると修正箇所が散らばって直しにくいため、シーン単位で確認する（balloon 内の `` `name` `` は変換スクリプトが自動で `<code>` 化するため、書き手側のチェック対象に含めなくてよい）。

## 関連

- `.claude/skills/write-hatena-diary/hatena-design.css`: 展開後 HTML の class（`.balloon` `.balloon-l` `.balloon-r` `.icon` `.text`）に対応する CSS。本ファイルとセットで運用
  - `.bluesky-embed` は `embed.bsky.app/static/embed.js` が描画するため CSS 側での定義は不要
- `scripts/convert_article_html.py`: 変換スクリプト本体
- `.claude/skills/publish-hatena/SKILL.md`: 投稿時に変換を呼び出す手順
