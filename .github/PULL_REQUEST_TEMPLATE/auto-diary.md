> **Note**: 本テンプレは `/auto-publish-diary` スキル専用です。
> GitHub Web UI から手動で PR を作る場合は、本文を全削除して書き直してください。
> 自動投稿スキル（`scripts/auto_publish_diary.py`）がプレースホルダを展開した本文を `gh pr create` に渡します。

## 自動投稿日記

- 記事タイトル: {{TITLE}}
- 投稿日: {{DATE}}
- 編集ページ（下書き・所有者のみアクセス可）: {{EDIT_URL}}
- 公開 URL（公開後に有効化）: {{PUBLIC_URL}}
- 記事ファイル: [{{ARTICLE_PATH}}]({{ARTICLE_PATH}})

---

このPRは `/auto-publish-diary` により自動生成されました。
