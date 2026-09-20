# auto-permanent-link

WordPress 記事のパーマリンク（slug）を、記事タイトルから **AI で英語スラッグ** として推奨する独立システム。
記事投稿画面のボタンを押すと、Bedrock Nova が英語・ハイフン区切り・概ね 30 文字以内の候補を提示し、
ユーザーが選んでパーマリンク欄へ反映する（提案型・自動書き込みなし）。

## 特徴

- **英語スラッグ**を生成（日本語タイトルでも URL がクリーン）
- **概ね 30 文字以内**・ハイフン区切りに正規化
- **投稿画面のボタンでオンデマンド**推奨（同期）
- 既存プロジェクトとは **完全分離**の独立スタック。
  共有するのは Bedrock Nova API を独立に呼ぶことのみ。WAF なし・VectorDB なし。

## 構成

| 層 | 実体 |
|----|------|
| バックエンド | AWS Lambda（Python 3.12 / 素のハンドラ）+ API Gateway、Bedrock Nova 2 Lite |
| フロント | WordPress プラグイン（投稿画面メタボックス + 候補カード UI） |
| 認証 | WordPress nonce + `edit_others_posts` 権限チェック（管理者・編集者のみ） |

詳細は `docs/design.md` を参照。

## ディレクトリ

- `aws/` — Lambda コード、CloudFormation テンプレート、ユニットテスト
- `wordpress/auto-permanent-link/` — WordPress プラグイン
- `docs/` — 設計仕様書

## 開発ステータス

- [x] Phase 1: 設計確定・プロジェクト雛形
- [x] Phase 2: AWS バックエンド実装
- [x] Phase 3: WordPress プラグイン実装
- [x] Phase 4: 検証（`aws/tests/` 25件パス、`scripts/verify.sh`、`docs/verification.md`）

## デプロイ運用

ビルド／デプロイ／S3 アップロードはユーザーが実施（既存プロジェクトと同運用）。
