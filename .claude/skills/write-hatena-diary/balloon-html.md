# 吹き出し / Bluesky 埋め込みの簡素記法

本ファイルは `/write-hatena-diary` が記事生成時に出力する吹き出し（balloon）と Bluesky 埋め込みの **簡素記法 → HTML 変換規約** を定める。
変換スクリプトは `scripts/convert_article_html.py`、起動は `/publish-hatena` 投稿時。

## 設計方針

- 生成スキルが書き出す `articles/hatena/*.md` は **簡素記法のまま** Git に保存する（HTML 直書きは禁止）
- 投稿時に `convert_article_html.py` が簡素記法を HTML に展開し、AtomPub の `<content>` にその HTML 入り Markdown を載せる
- balloon は **行頭マーカーで始まる単行記法**（閉じトークン不要）
- bluesky は **非対称フェンス** `{{{bluesky` 〜 `}}}` で囲む（複数行・複数キー必須のため）
- ブロック内本文は **HTML 直書き**として扱う（Markdown 構文は解釈されない）。例外として `` `name` `` 形式のインラインコードと Markdown 風文字装飾は、変換スクリプトが対応 HTML タグへ自動置換する

## balloon 記法

行頭マーカー `kuro-chan>>` / `nee-san>>` から行末までを 1 セリフとする。閉じトークンは不要。マーカーは **必ず行頭から書く**（前置空白を入れるとサイレントに地の文として通過する）。CSS クラス名は `balloon-l` / `balloon-r` のまま（変換器がマッピングする）。

### `kuro-chan>>` — クロちゃん（左の話者）

書き方:

```
kuro-chan>>ぼく、ちょっと相談があるんですが。
```

展開後 HTML（1 行に圧縮される）:

```html
<div class="balloon balloon-l"><div class="icon"></div><div class="text">ぼく、ちょっと相談があるんですが。</div></div>
```

### `nee-san>>` — 幸田姉さん（右の話者）

書き方:

```
nee-san>>あら、どうしたの。
```

展開後 HTML:

```html
<div class="balloon balloon-r"><div class="icon"></div><div class="text">あら、どうしたの。</div></div>
```

### マーカー直後の空白

マーカー `>>` 直後の半角スペースは **任意**。パーサが先頭空白を trim するため、以下はいずれも同じ HTML を生成する。

```
kuro-chan>>メッセージ
kuro-chan>> メッセージ
kuro-chan>>   メッセージ
```

### 1 行 1 セリフ（長文の扱い）

balloon は **1 行 = 1 セリフ** を原則とする。長文セリフは:

- できる限り短く書く（簡潔性を優先）
- どうしても改行を入れたい場合は HTML `<br/>` で疑似改行する

```
nee-san>>1 段落目で言いたいこと。<br/>2 段落目で続きを言う。
```

マーカーなしの後続行は balloon の続きとして扱わない（地の文として通過する）。

### 本文に含められるもの

- 通常の文字列
- インラインコード `` `name` `` 形式（変換時に自動で `<code>name</code>` に置換される）
- Markdown 風の文字装飾（変換時に対応 HTML タグへ自動置換される）:
  - `***foo***` → `<strong><em>foo</em></strong>`（太字+斜体）
  - `**foo**` → `<strong>foo</strong>`（太字）
  - `*foo*` → `<em>foo</em>`（斜体）
  - `~~foo~~` → `<del>foo</del>`（取り消し線）
  - 装飾の境界条件: 内側の最初と最後が **非空白** であることを要求する。地の文の単独 `*` `**` `~~`（例: `2 * 3 = 6` や `2 ** 3 = 8`）はリテラルのまま残る
  - 装飾 4 種いずれも `<code>...</code>` の **外側** にのみ作用する。`` `**foo**` `` `` `*foo*` `` `` `~~foo~~` `` のようにインラインコード内に装飾文字を書いた場合は `<code>**foo**</code>` 等としてリテラル維持される
  - アンダースコア形式（`__bold__` / `_italic_`）は非対応（日本語混じり文で誤爆しやすいため）
- `<code>...</code>` `<br/>` 等のインライン HTML タグ（直書きも可。`<code>` は backtick と併用すると二重囲みになるため、どちらか片方のみ使う）

含められないもの:

- ブロックレベル要素（`<p>` `<div>` 等）— 既存 `.text` div の中で破綻するため

## Bluesky 記法

### `{{{bluesky` 〜 `}}}` — Bluesky 投稿の埋め込み

書き方:

```
{{{bluesky
did=did:plc:xxxxxxxxxxxxxxxxxxxxxxxx
cid=bafyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
rkey=3xxxxxxxxxxxx
handle=example.bsky.social
display-name=表示名
created-at=2026-05-14T10:33:34.400+09:00
lang=ja
text=投稿本文を 1 行で書く
}}}
```

開閉のマーカーが視覚的に対応する（`{{{` / `}}}`）ため、閉じ忘れが起きにくい設計。

展開後 HTML（はてなブログ Markdown モードで投稿カードとして描画される）:

```html
<blockquote class="bluesky-embed" data-bluesky-uri="at://did:plc:xxx.../app.bsky.feed.post/3xxx..." data-bluesky-cid="bafyxxx...">
<p lang="ja">投稿本文を 1 行で書く</p>
— <a href="https://bsky.app/profile/did:plc:xxx...?ref_src=embed">表示名 (@example.bsky.social)</a> <a href="https://bsky.app/profile/did:plc:xxx.../post/3xxx...?ref_src=embed">2026-05-14T10:33:34.400+09:00</a></blockquote>
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
| `created-at` | 必須 | 投稿日時（ISO 8601 形式、JST `+09:00` オフセット必須） |
| `text` | 必須 | 投稿本文。改行を含めるときは `\n` 文字を埋めるのではなく、後述「複数行 text の扱い」に従う |
| `lang` | 任意 | 言語コード。省略時は `ja` |

### 複数行 text の扱い

Bluesky の投稿本文に改行が含まれる場合は、`text=` の値を **複数行に分けて書く**:

```
{{{bluesky
did=did:plc:xxx
cid=bafyxxx
rkey=3xxx
handle=example.bsky.social
display-name=表示名
created-at=2026-05-14T10:33:34.400+09:00
text=1 行目
2 行目
3 行目
}}}
```

`text=` で始まる行以降、閉じ `}}}` までを `text` の値として連結する（改行をそのまま保持）。
そのため `text=` は **ブロック内の最後のキー** として配置すること。

すべての値は HTML エスケープされてから展開される（`<` `>` `&` `"` 等は安全な実体参照になる）。

`text=` 行以降は値として連結されるため、入れ子検知（`{{{bluesky` / `kuro-chan>>` / `nee-san>>` の検出）の対象外となる。Bluesky 投稿本文にこれらのトークン文字列が含まれていても `text` 値の一部として通過する。

## 非変換領域

簡素記法ブロックの外（地の文・H2 見出し・通常 Markdown 段落）はそのままパススルーされる。
balloon を使わない記事（例: イベント告知記事等）は変換スクリプトを通しても無変換で出力される。

## エラー条件

変換スクリプトが停止する条件:

| 条件 | 理由 |
|---|---|
| `{{{bluesky` の閉じ `}}}` がないままファイル末尾に到達 | 未閉鎖ブロック |
| `{{{bluesky` ブロックで必須キーが欠落している | 埋め込み URL を組み立てられない |
| `{{{bluesky` ブロック内に別のブロック開始（`{{{bluesky` / `kuro-chan>>` / `nee-san>>`）が現れた | 入れ子は未サポート |
| 対応する `{{{bluesky` のない孤立した `}}}` を検出 | 開きマーカーの誤記（`{{bluesky` 等）に書き手が気づけるよう停止 |
| `{{{bluesky` ブロック内（`text=` 行より前）に空行・`key=value` 形式でない行を検出 | 不明な行の混入による解釈ぶれを防止 |
| `created-at` の値が JST `+09:00` オフセットの ISO 8601 形式でない | 時刻表記の統一（UTC・他タイムゾーン・パース不能値は受け付けない） |

## 書き手向けチェックリスト

### 1. balloon は 1 行 1 セリフ

balloon は閉じトークン不要の単行記法。1 行 1 セリフを書き、複数行に渡らせない。マーカーなしの後続行は地の文として通過するため、続きとして扱われない。

❌ 悪い例:

```
kuro-chan>>セリフ 1 行目
これは続きの 2 行目のつもり（balloon にならず地の文になる）
```

✅ 良い例:

```
kuro-chan>>セリフ 1 行目
kuro-chan>>セリフ 2 行目として独立した発話にする
```

長文セリフは `<br/>` で疑似改行:

```
nee-san>>1 段落目の内容。<br/>2 段落目の内容。
```

### 2. bluesky フェンスの閉じ `}}}` を忘れない

`{{{bluesky` で開いたら必ず `}}}` で閉じる。閉じ忘れるとファイル末尾までブロックが続いていると解釈され、`未閉鎖ブロック` エラーで停止する。

❌ 悪い例（閉じ忘れ）:

```
{{{bluesky
did=...
text=投稿本文

## 次のシーン
```

✅ 良い例:

```
{{{bluesky
did=...
text=投稿本文
}}}

## 次のシーン
```

書いた直後の自己チェック: `{{{bluesky` を書いたら、その場で `}}}` まで書ききってから中身を埋める。マーカーが視覚的に対応する形（`{{{` / `}}}`）なので、ペアが揃っているか目視で判定しやすい。

### 3. bluesky フェンス内に別のブロック開始を入れない

入れ子は未サポート。`{{{bluesky` の中に `kuro-chan>>` などを書くと `入れ子は未サポート` エラーで停止する。balloon と bluesky は **独立したブロック** として並べる。

✅ 良い例（セリフ → 投稿 → セリフ）:

```
kuro-chan>>姉さん、見てください。

{{{bluesky
did=...
text=投稿本文
}}}

nee-san>>あの人ね…
```

### 4. balloon 内のリポ名・コード断片・文字装飾は通常の Markdown 記法で書く

balloon 内では `` `name` `` → `<code>name</code>` への自動置換、`**bold**` → `<strong>bold</strong>` への自動置換が効く。書き手は balloon の **内外を問わず** 通常の Markdown 記法で書ける。

```
kuro-chan>>`agent-commons` のルール書き直しが入りました。**ここが重要** です。
```

`<code>...</code>` を直接書いてもよい（HTML 直書きとして通る）。ただし `<code>` と backtick の併用は二重囲みになるため避ける。

## CSS 連携

展開後 HTML の class（`.balloon` `.balloon-l` `.balloon-r` `.icon` `.text`）に対応する CSS は `.claude/skills/write-hatena-diary/hatena-design.css` を参照。**スマホ表示用の `@media (max-width: 600px)` 調整も同ファイルに集約済み**。

はてなブログ管理画面への CSS 登録手順は `hatena-design.css` ファイル冒頭のコメントを参照。

## 関連

- `.claude/skills/write-hatena-diary/hatena-design.css`: balloon の見た目 + スマホ調整 CSS
  - `.bluesky-embed` は `embed.bsky.app/static/embed.js` が描画するため CSS 側での定義は不要
- `scripts/convert_article_html.py`: 変換スクリプト本体
- `.claude/skills/publish-hatena/SKILL.md`: 投稿時に変換を呼び出す手順
