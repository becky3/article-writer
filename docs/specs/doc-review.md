# article-writer プロジェクト固有の doc-review 追加基準

doc-review スキル（agent-commons 側）が `docs/specs/**/doc-review*.md` を Glob 検索して併用する追加基準ファイル。

## 除外対象

以下のパターンに該当するファイルは doc-review の対象から除外する。

- `articles/**/*.md`: 生成記事（はてな日記 / Zenn 等）

## 理由

生成記事は `/write-hatena-diary` 経由で `/review-hatena-diary` の専用観点（物語ガイド遵守 / ガイドライン準拠 / 言及正確性 / 対話整合性）で別途レビューする設計。汎用ドキュメント観点（doc-review スキル）と観点が重複し、過剰指摘の原因になるため除外する。
