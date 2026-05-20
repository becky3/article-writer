> **Note**: 本テンプレは `/auto-publish-diary` スキル専用です。
> GitHub Web UI から手動で PR を作る場合は、本文を全削除して書き直してください。
> 自動投稿スキル側は `gh pr create --body-file` 経由でプレースホルダ展開された本文を渡します。

## 自動投稿日記

- 記事タイトル: {{TITLE}}
- 投稿日: {{DATE}}
- 公開予定 URL（下書き登録済み、公開時に有効化）: {{DRAFT_URL}}
- 記事ファイル: [{{ARTICLE_PATH}}]({{ARTICLE_PATH}})

---

このPRは `/auto-publish-diary` により自動生成されました。
