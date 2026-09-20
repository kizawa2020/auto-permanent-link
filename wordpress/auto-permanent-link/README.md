# Auto Permanent Link — WordPress プラグイン

記事投稿画面のメタボックスにある「候補を生成」ボタンで、記事タイトルから
**英語スラッグ（概ね30字以内）** の候補を AI が提案し、選んでパーマリンク欄へ反映する。
提案型で、自動書き込みはしない。

## インストール

1. `auto-permanent-link/` ディレクトリを `wp-content/plugins/` に配置。
2. 管理画面「プラグイン」で **Auto Permanent Link** を有効化。
3. 「設定 → Auto Permanent Link」で以下を入力:
   - **API エンドポイント URL**: CloudFormation Outputs の `ApiEndpoint`（末尾 `/suggest` は付けない）
   - **共有シークレット (X-Api-Secret)**: デプロイ時の `SharedSecret` と同じ値
   - **API キー (x-api-key)**: `aws apigateway get-api-keys --include-values` で取得した値

## 使い方

1. 投稿の編集画面を開く（Classic / Gutenberg 両対応）。
2. 右サイドの「パーマリンク推奨」メタボックスで「候補を生成」を押す。
3. 候補（英語 slug と文字数）が最大3件表示される。
4. 各候補の「適用」を押すと、選んだ slug がメタボックスの隠しフィールドに保持される
   （編集画面のパーマリンク表示は参考プレビュー）。
5. **投稿を「更新」または「公開」して保存すると、サーバー側で slug が確定**する。

> **なぜ保存で確定する方式なのか**: WordPress コアの編集画面 JS は保存直前に
> 隠し `#post_name` を上書き（空リセット）するため、フロントで slug を書いても
> 「一瞬入って戻る」現象が起きる。これを根絶するため、フロントは値を保持するだけにし、
> 保存時に `wp_insert_post_data` フック（`class-apl-save.php`）でサーバーが `post_name` を
> 強制する。コア JS の書き戻しと構造的に競合しない。

## セキュリティ・表示権限

- **表示権限**: メタボックスと JS/CSS は **`edit_others_posts` 権限を持つユーザーのみ**に配布・表示。
  これは **管理者(Administrator)・編集者(Editor)** に該当し、**投稿者(Author)・寄稿者(Contributor)
  には表示されない**。
- REST ルート `POST /wp-json/auto-permanent-link/v1/suggest` は
  **X-WP-Nonce 検証 + `edit_others_posts` 権限チェック**を通ったリクエストのみ処理（表示条件と同一境界）。
- 共有シークレット (A) と API キー (B) は **PHP から Lambda へ送るだけ**で、ブラウザ／JS には一切出さない。
- Lambda 側は `X-Api-Secret` を定数時間比較し、API Gateway は `x-api-key` とレート制限で保護。

## ファイル構成

```
auto-permanent-link/
├── auto-permanent-link.php        プラグイン本体（定数・ブートストラップ）
├── includes/
│   ├── class-apl-settings.php     設定ページ
│   ├── class-apl-metabox.php      投稿画面メタボックス + asset enqueue + 隠しフィールド
│   ├── class-apl-rest.php         REST ハンドラ（nonce+権限 → Lambda プロキシ）
│   └── class-apl-save.php         保存時 slug 確定（wp_insert_post_data フック）
└── assets/
    ├── js/admin.js                候補生成・表示・隠しフィールドへ slug 保持
    └── css/admin.css              スタイル
```
