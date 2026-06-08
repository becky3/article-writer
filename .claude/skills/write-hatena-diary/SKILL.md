---
name: write-hatena-diary
description: はてなブログ向けの日記記事を、指定日のジャーナルと Bluesky 投稿を素材に 1 日 1 本生成する
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Skill, mcp__rag-knowledge-production__rag_list_by_date_range, mcp__rag-knowledge-production__rag_get_document
argument-hint: "[YYYY-MM-DD | MM-DD] [--auto-publish]"
---

## タスク

指定日のジャーナル（必須）と Bluesky 投稿（補足）を素材に、はてなブログ向けの日記 Markdown を生成する。
本スキルは **1 回の起動で 1 日分の記事 1 本** を生成する単一日モードのみをサポートする。複数日執筆が必要なら本スキルを複数回起動すること。
執筆ガイドは品質ルール（媒体共通）と物語世界（書き手ペルソナ）の 2 ファイルに分離している。
`.claude/skills/write-hatena-diary/quality-guidelines.md` が必ず守る絶対原則の SSoT（構造・記法・禁止情報・事実正確性等）、
`.claude/skills/write-hatena-diary/narrative-guidelines.md` が物語世界と書き方の SSoT（キャラクター・関係性・社長・読者像・素材の扱い・タイトルの付け方・文体・解説・地の文等）。
`/review-hatena-diary` の各観点もこの 2 ファイルを機械照合する。
記事テンプレートは `.claude/skills/write-hatena-diary/template-diary.md` を SSoT とする。
吹き出し・Bluesky 埋め込みの簡素記法は `.claude/skills/write-hatena-diary/balloon-html.md` を参照。
変換は `/publish-hatena` 投稿時に `scripts/convert_article_html.py` が行う。
本スキルは簡素記法を `articles/hatena/*.md` に書き出すまでを担い、HTML 展開は行わない。

## 引数

`$ARGUMENTS` の形式:

- **引数なし**: 過去執筆記事最新日の翌日から実行日までを 1 日ずつ前進してジャーナル存在日を探し、最初に見つかった 1 日分の日記 1 記事を生成（auto-next モード）。次のいずれかではエラー停止: (a) `articles/hatena/` に過去記事が無い、(b) 過去執筆記事最新日が実行日以降で探索範囲が空、(c) 探索範囲（過去最新 +1 日 .. 実行日）にジャーナル存在日が無い
- **`<YYYY-MM-DD>`**: 指定日 1 日分の日記 1 記事
- **`<MM-DD>`**: 実行日の年を補完して `YYYY-MM-DD` 扱い、1 記事
- **`--auto-publish`**: 任意。`/auto-publish-diary` 経由で起動される無人実行モード。日付選定軸（auto-next / 単一日指定）と直交した独立軸として動作する:
  - Phase 9（自動レビュー）: `/review-hatena-diary <パス> --auto-publish` を渡し、レビュー結果を triage ではなく書き手自己判断で適用させる
  - Phase 10（完了出力）: エディタオープンを省略し、`/auto-publish-diary` が抽出する構造化メッセージを出力する

## 処理手順 (Phase 1〜10)

本スキルは Phase 1 から Phase 10 までを **1〜10 のフラット連番** で順に実行する。サブ Phase（Phase X-Y）の階層構造は持たない。1 日 = 1 記事の単一直線フロー。

| # | Phase | 役割 |
|---|---|---|
| 1 | 引数パース | `$ARGUMENTS` から `TARGET_DATE` と `AUTO_PUBLISH` を確定 |
| 2 | 対象日の確定 | ジャーナル存在を確認し `TARGET_DATE` を確定（auto-next モード）/ 検証（単一日指定モード） |
| 3 | 執筆前準備 | ガイド・テンプレート Read と過去記事メモを 1 つの Phase で実施 |
| 4 | 素材取得 | 当該日のジャーナル全文・Bluesky 投稿を MCP 経由で取得 |
| 5 | 関連リポジトリ・Issue/PR の事実確認 | 記事化前に対象の事実を確認し誤認を防ぐ |
| 6 | Bluesky 選別 | 引用候補を選ぶ |
| 7 | 記事生成 | 進行パターン選定 + 本文執筆 |
| 8 | ファイル出力 | `articles/hatena/{date}-diary.md` を Write |
| 9 | 自動レビュー | `/review-hatena-diary` を呼び出し |
| 10 | 完了出力 | `📁 生成記事:` を含む構造化メッセージを必ず出力（critical path） |

**Phase 10 は必須実行**。Phase 9 で `/review-hatena-diary` が完了しても、本スキル全体の完了出力は Phase 10 が単独で担う。Phase 9 の完了通知（`✅ /review-hatena-diary 完了`）と Phase 10 の完了通知（`✅ /write-hatena-diary 完了`）は別物。

### Phase 1: 引数パース

1. `$ARGUMENTS` を空白で分割し、トークンリストを得る
2. **オプション抽出**: トークンリストから `--auto-publish` を見つけたら `AUTO_PUBLISH=1` を設定し、当該トークンをリストから除外する（位置はリスト内のどこでもよい）
3. **未知オプションのバリデーション**: 除外後のリスト内に `--` で始まるトークンが残っていれば `エラー: 未知のオプションです: <トークン>` で停止する
4. **日付トークン抽出**: 除外後のリストの最初の非空要素を `RAW_ARG` とする
5. **モード判定と日付確定**:
   - `RAW_ARG` が空文字列 → **auto-next モード**へ進む（下記 6）
   - `RAW_ARG` が非空 → 単一日指定として `parse_date(RAW_ARG)` を適用し、`TARGET_DATE` に格納する（下記 7）
6. **auto-next モードでの日付決定**:
   1. `articles/hatena/` を走査し、ファイル名 `YYYY-MM-DD-*.md` から日付を抽出。最も新しい日付を `D_last` とする
   2. 過去記事が 0 件で `D_last` が取得できない場合はエラー停止:

      ```text
      エラー: articles/hatena/ に過去記事が存在しません。初回実行は日付指定（YYYY-MM-DD）で起動してください
      ```

   3. `D_last + 1 日` を `DATE_FROM`、実行日のローカル日付を `DATE_TO` とする探索範囲を確定。`DATE_FROM > DATE_TO` の場合はエラー停止:

      ```text
      エラー: 過去執筆記事最新日（<D_last>）が実行日以降のため自動探索対象日がありません。日付を明示指定してください
      ```

   4. 確定した探索範囲は Phase 2 でジャーナル存在を見て 1 日に絞り込む（本 Phase では `TARGET_DATE` は未確定）
7. **単一日指定での `TARGET_DATE` 確定**: `parse_date` の結果をそのまま `TARGET_DATE` に格納する。`DATE_FROM`/`DATE_TO` は使用しない

**`articles/hatena/` 日付抽出の振る舞い:**

| 入力ファイル名 | 処理 |
|---|---|
| `YYYY-MM-DD-*.md`（先頭 10 文字が日付として有効） | `YYYY-MM-DD` を採用 |
| 上記に合致しない（先頭 10 文字が日付形式でない・存在しない日付） | スキップ（候補から除外） |
| `published.jsonl` 等の Markdown 以外 | 走査対象外 |

**`parse_date` の振る舞い:**

| 入力形式 | 処理 |
|---|---|
| `YYYY-MM-DD`（10 文字、ハイフン位置 4,7） | そのまま採用 |
| `MM-DD` / `M-D` 等（ハイフン 1 個、最大 5 文字） | 実行日の年を補完して `YYYY-MM-DD` に組み立て |
| その他 | エラー停止: `エラー: 日付形式を解釈できません: '<入力>'。YYYY-MM-DD または MM-DD で指定してください` |

### Phase 2: 対象日の確定（ジャーナル存在の確認）

素材の全文取得はここでは行わない。`TARGET_DATE` 候補のジャーナルが存在することを一覧照会で確認する。素材の全文取得は Phase 4 で実施する。

1. **auto-next モード**（Phase 1 で `TARGET_DATE` 未確定）:
   1. `rag_list_by_date_range(date_from=DATE_FROM, date_to=DATE_TO, source_type="journal", limit=100)` でジャーナル一覧を取得（`limit` はデフォルト 20 では取り切れないため大きく明示）
   2. 結果から日付昇順で最も古い 1 日を `TARGET_DATE` として採用
   3. ジャーナルが 1 件も見つからなければエラー停止:

      ```text
      エラー: 過去執筆記事最新日の翌日（<DATE_FROM>）から実行日（<DATE_TO>）までジャーナルが見つかりませんでした。
      日記の素材になるジャーナルがないため執筆を停止します。
      ```

   4. 確定した日を情報メッセージで通知:

      ```text
      情報: auto-next: <TARGET_DATE> を執筆対象として選択しました
      ```

2. **単一日指定モード**（Phase 1 で `TARGET_DATE` 確定済み）:
   1. `rag_list_by_date_range(date_from=TARGET_DATE, date_to=TARGET_DATE, source_type="journal", limit=100)` でジャーナル存在を確認
   2. 0 件ならエラー停止:

      ```text
      エラー: 対象日（<TARGET_DATE>）のジャーナルが見つかりませんでした。
      日記はジャーナルを必須素材としています。日付指定を見直してください。
      ```

### Phase 3: 執筆前準備（共通リソース + 過去記事メモ）

執筆に必要なものを Phase 4 以降の前にまとめて読み込む。

1. **執筆ガイド・テンプレート Read**: `quality-guidelines.md` / `narrative-guidelines.md` / `template-diary.md` を Read する。読み込んだ内容は Phase 7（記事生成）で共通利用する
2. **過去記事メモ作成**: 過去記事を読み、今回の執筆改善につながる点を自分の言葉でメモする（本スキル内で `/review-hatena-diary` は呼ばない。Phase 9 の自動レビューとは別概念）
   - 対象範囲: `articles/hatena/` 直下の `YYYY-MM-DD-*.md` のみ。`articles/hatena/archive/` は除外。ファイル名先頭 10 文字（`YYYY-MM-DD`）で日付降順ソートし、最新 12 本を Read する（Phase 1 の日付抽出規則と同じ）
   - 過去記事が 12 本未満ならある分だけを対象。0 件でもエラーにせず、メモなしで Phase 4 に進む
   - メモ先: `.tmp/hatena-improvement-memo/<TARGET_DATE>.md`（例: `.tmp/hatena-improvement-memo/2026-05-13.md`）。ディレクトリが存在しなければ作成。同名ファイルがあれば上書き。`.tmp/` は `.gitignore` 対象で commit に含まれない
   - メモの観点・軸は本スキルでは指定しない。書き手が自由に「今回の執筆で改善できる点」を言葉にする（チェック項目化・観点列挙はしない。指標化すると指標だけ最適化される Goodhart 化を避ける）
   - Phase 7（記事生成）で同ファイルを Read して執筆に反映する

### Phase 4: 素材取得

1. 当該日（`TARGET_DATE`）のジャーナルを `rag_get_document(source_id=...)` で全文取得する
2. `rag_list_by_date_range(date_from=TARGET_DATE, date_to=TARGET_DATE, source_type="bluesky", limit=100)` で当該日の Bluesky 投稿一覧を取得する（**本ステップは必須実行**、0 件でも続行）
3. 各投稿について `rag_get_document(source_id=..., format="original")` で投稿 JSON 全体を取得する。

    **`format="original"` 指定必須**（デフォルトの `format="text"` では本文以外のメタデータが失われ、`cid` 等が取得できない）。

    取得した JSON から以下のフィールドを抽出して Phase 7（記事生成）で `{{{bluesky ... }}}` 簡素記法ブロックの key=value 値として埋め込む:

    | キー | JSON パス |
    |---|---|
    | `did` | `post.author.did` |
    | `cid` | `post.cid` |
    | `rkey` | `post.uri` の末尾（`at://<did>/app.bsky.feed.post/<rkey>` の `<rkey>` 部分） |
    | `handle` | `post.author.handle` |
    | `display-name` | `post.author.displayName` |
    | `created-at` | `post.record.createdAt` を `python scripts/convert_utc_to_jst.py <値>` に通して得た JST ISO 8601 文字列（`+09:00` オフセット付き） |
    | `text` | `post.record.text` |
    | `lang` | `post.record.langs[0]`（任意。省略時は `{{{bluesky ... }}}` 側のデフォルト `ja` が適用される） |

    Bluesky 投稿の時刻情報は本記事全体で JST として扱うこと（時刻への直接言及・前後関係・暗示的な時系列描写を含む全ての記述において）。

### Phase 5: 関連リポジトリ・Issue/PR の事実確認

記事化前に、当該日のジャーナルが扱う対象の事実を確認する。リポジトリと機能の取り違え・役割の誤認を防ぐ。

1. **対象リポジトリの特定**: ジャーナルの `source_id`（`journal/<repo>/...`）からリポジトリ名を取得し、`.claude/sources.yml` の `owner/name` を引き当てる
2. **リポジトリ実態の把握**: 環境変数 `LOCAL_REPOS_ROOT` からローカルパス（`${LOCAL_REPOS_ROOT}/<owner>/<name>`）を解決し、`README.md` および `docs/specs/overview.md` 等を読む
   - リポジトリ全体の役割と、ジャーナルが扱う対象が「リポジトリ全体」か「その一機能」かの境界を確認する
   - ローカル不在・`LOCAL_REPOS_ROOT` 未設定時は `gh`（`gh repo view <owner/name>`・`gh api` での README 取得）にフォールバックする
3. **関連 Issue/PR の確認**: ジャーナル本文に記載された Issue/PR 番号のうち、記事で扱う見込みのエピソードに対応するものを `gh issue view <番号> --repo <owner/name>` / `gh pr view <番号> --repo <owner/name>` で確認し、背景・変更点・経緯を把握する。全件確認は不要（採用エピソードの 1〜2 件に絞る）
4. 確認した事実を Phase 7（記事生成）に反映する。リポジトリ名・機能名・役割は確認結果と整合させ、ジャーナルや思い込みだけに基づく断定をしない

### Phase 6: Bluesky 選別

1. 当該日の Bluesky 投稿が 0 件なら本 Phase をスキップして Phase 7 へ
2. 投稿は話題を問わず引用候補になる。技術・私的（日常・趣味等）の別で除外しない
3. 記事の素材・対比・オチに使える投稿を当該日の「引用候補」セットに残す。使わない投稿があってもよい
4. 引用候補を 1 件も採らない場合: Phase 7 では当該日の Bluesky 言及・引用とも設けない（言及だけ・引用なしは不可）

### Phase 7: 記事生成

**まず進行パターンを 1 つ決める**（記事の構成方針。候補一覧（ID）と定義は `narrative-guidelines.md`「進行パターン」が SSoT）:

1. **素材合致を最優先**: その日のジャーナル素材が特定のパターンに明確に強く合致する場合は、そのパターンを選ぶ。これは直近の使用有無より優先する（強く合致するなら直近で使った型でも選んでよい）
2. **明確な強い合致がなければ、`python scripts/select_pattern.py` を実行し、出力された ID を採用する**
   - スクリプトの処理: `narrative-guidelines.md`「進行パターン」から ID 一覧を抽出 → 既存記事フロントマターの直近 5 件の `pattern` を除外 → 残りから乱数で 1 つ選ぶ
   - 手順をスクリプトに固定し実行者によるブレをなくす。選定ロジックの SSoT は `scripts/select_pattern.py`、ID の SSoT は `narrative-guidelines.md`「進行パターン」
3. 選んだ ID を当該記事のフロントマターに `pattern: <ID>` として書く（フロントマター生成時に含める。`title`/`date`/`category` と同じメタ情報）。パターンはトーン・展開方針として本文に反映するが、**ID・パターン名を本文には書かない**。published.jsonl への転記は publish 時に `publish_hatena.py` が自動で行う
4. 選んだパターンの定義文（`narrative-guidelines.md`「進行パターン」の当該 ID）を読み返し、その定義を本文全体の支配的な構成・トーン方針として明示的に据えてから書く。定義から外れて平常運転に収束させない

続いて本文を書く。**Phase 3 で `.tmp/hatena-improvement-memo/<TARGET_DATE>.md` に書き出したメモを Read し、その改善点を今回の執筆に反映する**。
Phase 3 で読んだ過去記事の表現・展開・締め方をそのまま再利用してはならない（焼き直し・既視感の回避）。
過去記事は改善方向に上書きするための参照であり、書き写すための参照ではない。
Phase 3 の対象（最新 12 本）以外の `articles/hatena/**`・`articles/hatena/archive/**` は本文執筆時に参照しない。
素材（ジャーナル・Bluesky）と物語世界の設定（`narrative-guidelines.md`）を主軸に、Phase 3 のメモを改善方向の指針として組み入れて新規に書く:

1. **本文の構成・口調・展開は `narrative-guidelines.md`（物語世界）を制御点として書き手の裁量に任せる**。固定セクション・必須サブセクションは設けない
2. **タイトル** の文字列は `narrative-guidelines.md`「タイトルの付け方」の方針に従って決め、フロントマター `title:` と本文 H1 を一致させる（一致ルールは `quality-guidelines.md`「タイトル一致」）
3. **リポを言及する箇所では `name` を backtick 付きで本文に直接書く**（例: `` `rag-knowledge` ``、`` `article-writer` ``）。`becky3/<name>` 形式・`#<番号>` 形式（Issue / PR）は使わない
4. **吹き出し** は `kuro-chan>>...` / `nee-san>>...` の単行マーカー記法で書く。記法仕様は `balloon-html.md` を参照。HTML タグ（`<div class="balloon">` 等）を直接書かない
5. **Bluesky 引用部** は `{{{bluesky ... }}}` のフェンス記法で書く
    - 記法仕様: `balloon-html.md` 「Bluesky 記法」
    - メタデータ: Phase 4（素材取得）で取得した key=value 形式（`did` / `cid` / `rkey` / `handle` / `display-name` / `created-at` / `text`、`lang` は任意）
    - 引用部の前提・関係性: `narrative-guidelines.md`「オーナー（社長）の位置づけ」「社長の SNS（Bluesky）について」を参照
6. **簡素記法ブロックの自己チェック**: シーンを書き終えるたびに `balloon-html.md` 「書き手向けチェックリスト」を確認する（balloon の 1 行 1 セリフ / bluesky フェンスの閉じ `}}}` / 入れ子禁止 等）。記事全体を書き終えてからまとめてチェックすると修正箇所が散らばるため、シーン単位で確認する
7. **セクション配置の順序**: タイトル H1 の直下に **登場人物セクション** を置き、続いて本文の H2 シーン、記事末尾に **プロジェクトの説明セクション** を置く。順序の SSoT は `template-diary.md` 冒頭の構造リストを参照
8. **登場人物セクション** をタイトル H1 直下に挿入する（言及リポ・対話シーン数に関わらず常に挿入）。固定 HTML 文言と置換ルールの SSoT は `template-diary.md` 「登場人物セクション」（マーカー全置換義務・字数・改変禁止範囲を含む）。置換内容の方針は `narrative-guidelines.md`「登場人物セクションの一言」を参照
9. **プロジェクトの説明セクション** を記事末尾に挿入する（常に挿入）。構造は `template-diary.md` 「プロジェクトの説明セクション」を参照

### Phase 8: ファイル出力

1 日 1 記事を前提とした命名で、`published.jsonl` の重複検知（`date:` キー）と整合する。

1. **出力先パス**: `articles/hatena/{TARGET_DATE}-diary.md`
2. ディレクトリが存在しなければ作成
3. **新規作成のため Write を使用**
4. 同名ファイルが既に存在する場合はエラー停止
5. 生成済みパスを `ARTICLE_PATH` として保持する（Phase 9・Phase 10 で参照）

進行パターン ID は Phase 7 でフロントマターに `pattern: <ID>` として書き込み済み。patterns.jsonl は使わない（published.jsonl への転記は publish 時に `publish_hatena.py` が自動で行う）。

### Phase 9: 自動レビュー

Phase 8 で当該日の記事を Write した直後、本 Phase で `/review-hatena-diary` を自動呼び出しする。生成 → review → triage → 修正 をコンテキストが新鮮なうちに完結させる。

1. `Skill` ツールで `/review-hatena-diary <ARTICLE_PATH>` を起動する。
   - `<ARTICLE_PATH>` は Phase 8 で Write した記事のリポジトリルートからの相対パス（例: `articles/hatena/2026-05-13-diary.md`）
   - `/review-hatena-diary` は絶対パス指定をエラー停止するため必ず相対パスで渡す
   - `AUTO_PUBLISH=1` の場合は引数末尾に `--auto-publish` を付与し、`/review-hatena-diary <ARTICLE_PATH> --auto-publish` の形で起動する
2. `/review-hatena-diary` 内で 4 観点並列レビュー → 指摘の triage 連携 / 書き手自己判断 → 確定した修正を対象記事ファイルへ適用する処理が完結する（本スキル側で追加の triage や修正適用は行わない）
3. `/review-hatena-diary` の完了通知（`✅ /review-hatena-diary 完了` 等のメッセージ）は **内側スキルの完了通知**であり、本スキル全体の完了出力ではない。`/review-hatena-diary` から制御が戻ったら、テキストを送出して締めずに必ず Phase 10 へ進む
4. `/review-hatena-diary` が正常終了しなかった場合（起動自体の失敗・内部停止・全サブエージェント失敗を含む）は警告を表示し、生成済み記事は残したまま Phase 10 へ進む（中断扱いにしない）

### Phase 10: 完了出力（必須実行・critical path）

本 Phase は **本スキル全体の完了点**。Phase 9 から戻った時点で必ず実行する。`AUTO_PUBLISH` の値で出力フォーマットを切り替えるが、いずれの場合も **本 Phase は実行される**。

#### `AUTO_PUBLISH=0`（通常モード）

1. `code "<ARTICLE_PATH の絶対パス>"` でエディタを起動（PATH 不通時はサイレントスキップ）
2. 完了メッセージを出力:

   ```text
   ✅ 日記を生成しました: articles/hatena/<TARGET_DATE>-diary.md
   ```

#### `AUTO_PUBLISH=1`（無人モード）

エディタオープンは行わない。`/auto-publish-diary` が抽出する構造化メッセージを **必ず** 出力する:

```text
✅ /write-hatena-diary 完了（auto-publish）
📁 生成記事: articles/hatena/<TARGET_DATE>-diary.md
```

`📁 生成記事: <相対パス>` の行は `/auto-publish-diary` がパースする critical path。この行が出力されないと親スキルの finalize（Hatena 投稿・git commit・PR・merge）が実行されない。Phase 9 で `/review-hatena-diary` が完了テキストを送出した直後でも、テキスト単独で締めず必ず本 Phase の出力まで進めること。

## 投稿（別スキル）

本スキルは記事生成までを担う。はてなブログへの下書き登録は `/publish-hatena` スキル（`.claude/skills/publish-hatena/SKILL.md`）で行う。`/publish-hatena` が `articles/hatena/published.jsonl` への記録追記も担当する。

**前提**: 1 日 1 記事。`published.jsonl` の重複検知は記事フロントマターの `date:`（日記対象日）を使う。

## エラーハンドリング一覧

各 Phase の本文に記述されたエラー挙動が SSoT。本テーブルは参照用の俯瞰表。

| ケース | 発生 Phase | 対応 | 詳細 |
|---|---|---|---|
| 引数の日付形式が不正 | Phase 1 | エラー表示 + 停止 | Phase 1 の `parse_date` 振る舞いテーブル |
| 未知のオプション（`--auto-publish` 以外の `--` 始まりトークン） | Phase 1 | エラー表示 + 停止 | Phase 1 ステップ 3 |
| auto-next モードで `articles/hatena/` に過去記事が 0 件 | Phase 1 | エラー表示 + 停止（日付指定を促す） | Phase 1 ステップ 6.2 |
| auto-next モードで過去執筆記事最新日が実行日以降 | Phase 1 | エラー表示 + 停止（探索対象日なし） | Phase 1 ステップ 6.3 |
| auto-next モードで探索範囲のジャーナル 0 件 | Phase 2 | エラー表示 + 停止 | Phase 2 ステップ 1.3 |
| 単一日指定で当該日のジャーナル 0 件 | Phase 2 | エラー表示 + 停止 | Phase 2 ステップ 2.2 |
| `rag_list_by_date_range` 接続失敗 | Phase 2 / 4 | `エラー: rag-knowledge-production MCP への接続を確認してください` 表示 + 停止 | — |
| 当該日の Bluesky 検索結果 0 件 | Phase 4 / 6 | Phase 6 をスキップ + 記事の Bluesky セクションを省略して続行 | Phase 6 ステップ 1 |
| Phase 8 のファイル出力で同名ファイルが既存 | Phase 8 | エラー表示 + 停止 | Phase 8 ステップ 4 |
| `/review-hatena-diary` が正常終了しなかった | Phase 9 | 警告表示 + 生成済み記事はそのままにして Phase 10 に進む（中断しない） | Phase 9 ステップ 4 |
| `code` PATH 不通 | Phase 10 | サイレントスキップ | Phase 10（通常モード） |

## ソース参照形式

`{source_type}:{source_id}` または `{source_type}:{source_id}#{fragment}`

例:

- ジャーナル全体: `journal:journal/agent-commons/20260513-...md`
- ジャーナル内の特定セクション: `journal:journal/agent-commons/20260513-...md#3`（3 番目の `###` 見出し）

`source_id` は `rag_list_by_date_range` / `rag_search` の結果に含まれる `Source` 値をそのまま使用する。
`rag_get_document(source_id=...)` で全文取得が可能。

## 記法ポリシー

詳細は `quality-guidelines.md`「記法」を SSoT とする。

## NFR と将来拡張

- **AtomPub 自動投稿**: `/publish-hatena` で下書き登録のみサポート。公開投稿（`<app:draft>no</app:draft>`）は別 Issue で扱う

## 注意事項

- 生成された記事は Phase 9 で `/review-hatena-diary` による自動レビュー（4 観点並列 + triage + 修正適用）を経た上で Phase 10 の完了出力に進む
- ペルソナ調整提案は記事生成中に行ってよいが、適用前にオーナー確認を取る（`narrative-guidelines.md`「ペルソナ調整に関する自己制御」参照）
- 著作物・IP 情報の混入を避ける（`quality-guidelines.md`「著作物・IP 情報の取り扱い」参照。`/review-hatena-diary` 観点 2「ガイドライン準拠」でも検出する）
