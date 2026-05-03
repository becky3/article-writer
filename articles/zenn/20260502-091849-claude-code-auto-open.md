## はじめに

Claudeが 「～を確認してください」、「～を変更しました」等として、mdやコードを言及するときがあるが、都度エクスプローラーを開いてファイルを開くのが面倒くさい。

Windowsの場合、VSCodeがインストールされてれば、 `code` というコマンドで、
対象ファイルを開かせる事ができます。

なので、Claudeがファイルを参照する際に、 `code` コマンドでファイルを開くように指示しておくと、いちいちファイルをたどらなくてよいので楽です。

この記事では、その使い方や活用例などを紹介します。

## Claude にエディタを開かせる

たとえば Claude が

```text
Claude > 計画ファイルを aidlc-docs/plan.md に生成しました。確認をお願いします。
```

といったように、確認依頼をしてきた際に、

```text
ユーザー > code で開いて
```

と、Claude が `code` を実行して対象ファイルを VS Code で開いてくれる。

![Claude が確認を促す→「code で開いて」と返す→ VS Code に対象ファイルが表示された状態のスクリーンショット](https://static.zenn.studio/user-upload/202e74bf0b45-20260502.png)

### 運用に組み込むなら: ルールに書いておく

毎回チャットで指示するのが面倒なら、Claude Code のルール（`~/.claude/rules/` 配下）に書いておく方法もある。Claude が確認依頼を出す直前に自発的に `code` を実行してくれるようになる。

```markdown:~/.claude/rules/invariants.md
ユーザーにドキュメントの確認を依頼する際は、対象ファイルを `code "<絶対パス>"` で開いてから確認依頼の本処理を行う。
```

このルールは [AI-DLC](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)（AI-Driven Development Lifecycle）のような、要件定義 → 設計 → 実装と段階を進めるたびに **生成ドキュメントへユーザーが回答・承認を書き込んで次に進める** ワークフローと相性が良い。

要件定義ステージで Claude が `aidlc-docs/`（AI-DLC が成果物を置くディレクトリ）配下の `requirements.md` を生成し、空欄の質問項目をユーザーに埋めさせる場面。Claude が `code` を実行すれば、ユーザーはそのファイルを VS Code 上で開いて即編集できる。

![AI-DLC のステージで Claude が aidlc-docs/ 配下のファイルを開かせ、ユーザーが回答を書き込んでいる様子](https://static.zenn.studio/user-upload/2c5b051d9ccd-20260502.png)

## 動かすための前提

### `code` を PATH に通す

`code` は VS Code 同梱の CLI（[公式リファレンス](https://code.visualstudio.com/docs/configure/command-line)）。

```bash
code --version
```

バージョン文字列が返れば OK。出なければ下表を参照。

| OS | 状態 | 対応 |
|---|---|---|
| Windows（インストーラー版） | 既定で PATH に追加済み | 通常は対応不要 |
| macOS | 既定では PATH に入らない | VS Code のコマンドパレットで `Shell Command: Install 'code' command in PATH` を実行 |
| Linux（.deb / .rpm / Snap） | 多くの場合 PATH に入る | 入っていなければシンボリックリンクを作成 |

### パスは二重引用符で囲む

パスに空白を含むと引数解釈が壊れるので、二重引用符で囲む。

```bash
code "C:/Users/My Name/projects/foo/plan.md"
```

## 補足: その他の使い方

### 特定行にジャンプして開く（`-g`）

該当行に飛ばす。レビュー指摘の対象行を見せたい場面で有効。

```bash
code -g "src/app.ts:42"
```

### 任意の 2 ファイルを差分エディタで並べる（`-d`）

VS Code 標準の差分エディタで 2 ファイルを左右に並べる。git は介在しないファイル比較。

```bash
code -d "before.md" "after.md"
```

### 標準入力をバッファに流し込む（`code -`）

`code -` は **標準入力を新規バッファに流し込む** 動作（左右比較ではなく単一バッファ）。`git diff` の出力をパイプで渡せば、diff 形式のハイライトで読める。

```bash
git diff | code -
```

## 応用: 同一ファイルの編集差分を split-diff で見る

split-diff は HEAD 版と作業ツリー版を左右 2 ペインで並べる表示形式。`code -` の単一バッファ表示と違い、対応する行が左右で揃う。

`git difftool` の外部ツールとして `code --diff` を呼び出す設定を渡せば実現できる。

```bash
git -c diff.tool=vscode \
    -c 'difftool.vscode.cmd=code --wait --diff "$LOCAL" "$REMOTE"' \
    difftool --no-prompt path/to/file
```

`--wait` がないと git が一時ファイルを掃除した後に VS Code が読みに行き、表示が壊れる。毎回の入力が面倒なら `git config` で永続化しておくと `git difftool path/to/file` だけで呼べる。

![既存の Python ファイルにテスト関数を追記した状態で `git difftool` を実行し、HEAD 版（左）と作業ツリー版（右）が VS Code の split-diff で並んで表示されているスクリーンショット](https://static.zenn.studio/user-upload/07c14ad06a22-20260502.png)

## まとめ

- チャットで「`code` で開いて」と頼めば、Claude が `code` を実行する
- 毎回頼むのが面倒なら、ルールに 1 行入れておくと自動で開く。AI-DLC のようにユーザー記入を伴うワークフローと相性が良い
- 前提は VS Code が PATH に通っていることだけ。パスは二重引用符で囲む
- `-g` の行ジャンプ、`-d` の差分、`code -` の標準入力流し込みなど、他にも使い方がある

## 余談: Claude に記事を書かせると新しい使い方が見つかる

本記事も Claude に下書きさせ、対話しながら検証・修正する形で執筆した。当初の主題は「ルールに 1 行入れて自動オープンさせる」だけだったが、執筆過程で `code` のオプションを Claude と一緒に試したことで、`-g` での行ジャンプ、`code -` への `git diff` パイプ、`git difftool` での split-diff 連携といった応用が芋づる式に見つかった。

公式ドキュメントには「自分の作業文脈に当てはめるとどう使えるか」までは書かれていない。Claude に記事の素案を書かせて、出てきた選択肢を対話で潰していく過程そのものが、ツールの使い方を再発見する手段になる。

:::message
本記事は開発ジャーナルを元に AI の支援を受けて執筆し、人がレビュー・編集しています。
:::
