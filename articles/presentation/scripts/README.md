# presentation scripts

発表資料作成で使う補助スクリプト群。

## 一覧

| スクリプト | 用途 |
|---|---|
| `build-marp.sh` | Marp 形式の Markdown から HTML / PDF を生成する |
| `generate-avatar.py` | GitHub アバターを取得して円形透過 PNG に変換する |

## build-marp.sh

Marp CLI を呼び出して HTML / PDF を生成する。`--allow-local-files` を自動で付けるため、ローカル画像を `![](xxx.png)` で参照している資料でも PDF 出力できる。

### 使い方

```bash
# HTML と PDF の両方を生成（第 2 引数を省略 または all を指定）
bash articles/presentation/scripts/build-marp.sh \
  "articles/presentation/2026-05-19_xxx/lt-2026-05-17-marp.md"

bash articles/presentation/scripts/build-marp.sh \
  "articles/presentation/2026-05-19_xxx/lt-2026-05-17-marp.md" all

# HTML のみ
bash articles/presentation/scripts/build-marp.sh \
  "articles/presentation/2026-05-19_xxx/lt-2026-05-17-marp.md" html

# PDF のみ
bash articles/presentation/scripts/build-marp.sh \
  "articles/presentation/2026-05-19_xxx/lt-2026-05-17-marp.md" pdf
```

出力は入力 Markdown と同じディレクトリに `<basename>.html` / `<basename>.pdf` として生成される。

### 前提

- bash（Git Bash 等の POSIX 互換シェル）
- Node.js (npx) が利用可能
- 初回実行時は `@marp-team/marp-cli` と Chromium がダウンロードされる

## generate-avatar.py

GitHub アバターを取得し、円形マスクを適用した透過 PNG として保存する。スライドの自己紹介ページなどで使う。

### 背景

CSS の `border-radius: 50%` で円形にクリップした画像を PDF に埋め込むと、一部のビューア（iPad の Books / Files / Safari 等）でクリップが正しく再現されず、矩形の背景が見えてしまうことがある。

画像自体を円形透過 PNG として用意すればビューア差異を回避できる。

### 使い方

```bash
# GitHub の数値 ID を指定（プロフィールページのアバター URL から取得可能）
python articles/presentation/scripts/generate-avatar.py 16248836 \
  articles/presentation/2026-05-19_xxx/avatar.png

# サイズ指定: GitHub から取得するアバターのピクセルサイズ（正方形の一辺、1〜2048、デフォルト 480）
python articles/presentation/scripts/generate-avatar.py 16248836 \
  articles/presentation/2026-05-19_xxx/avatar.png --size 800
```

GitHub 数値 ID は `https://api.github.com/users/<username>` の `id` フィールド、または既存アバター URL（`https://avatars.githubusercontent.com/u/<ID>?v=4`）から取得できる。

### 前提

- Python 3.x
- Pillow (`pip install Pillow` または `uv add Pillow`)
- `avatars.githubusercontent.com` への HTTPS アクセスが可能な環境

### スライド側の記述例

```markdown
![](avatar.png)
```

CSS は `border-radius` を付けなくてよい（画像が既に円形）。

```css
.profile img {
  width: 240px;
  height: 240px;
  object-fit: cover;
  flex-shrink: 0;
}
```
