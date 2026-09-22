# CHANGES

## 1.0.0 — 初回リリース

WordPress 記事タイトルから AI（Bedrock Nova 2 Lite）で英語スラッグ（パーマリンク）を提案する、
独立した AWS バックエンド + WordPress プラグイン。既存プロジェクトとは完全分離の専用スタック。

### バックエンド（AWS）
- **素の Lambda ハンドラ**（`app.lambda_handler` / Python 3.12、API Gateway REST プロキシ統合）。
  外部依存は boto3（ランタイム同梱）のみ。FastAPI / uvicorn / Lambda Web Adapter は使わない。
- Bedrock Nova 2 Lite（`jp.amazon.nova-2-lite-v1:0`、環境変数 `MODEL_ID` で変更可）を Converse API で呼び、
  numbered JSON `[{"i","slug"}]` を index マッピングで受領。
- slug 正規化（`slug.py`）: NFKC → 英小文字 → ハイフン化 → **30 字以内（ハイフン境界優先）** → 重複除去 → フォールバック。
  モデル出力を信頼せず、長さ・文字種は Lambda 側で必ず担保。
- 「もう一度生成」で別候補：既出 slug を `exclude` で除外し、`variety` 時は生成温度を上げて多様化。
- **素の CloudFormation テンプレート**（SAM ではない）: IAM Role / Lambda / API Gateway（/suggest・/health・OPTIONS）
  / Deployment / Stage / ApiKey / UsagePlan を明示。Lambda コードは S3 参照方式。WAF なし・VectorDB なし。
- パッケージングは手動 zip（`.py` のみを固める。依存は boto3 のみでランタイム同梱）。

### セキュリティ（二段構え）
- **(A) 共有シークレットヘッダー** `X-Api-Secret` を Lambda が `hmac.compare_digest`（定数時間比較）。
  不一致/欠損は 401、サーバー側未設定は 503（ノーガード公開を防ぐ安全側フェイル）。`/health` は認証不要。
- **(B) API Gateway APIキー + Usage Plan**（レート 5 req/s・burst 10・日次 500）でコスト暴走を上限化。
- シークレット/APIキーは WordPress の PHP から Lambda へ送るのみで、ブラウザ／JS には出さない。

### WordPress プラグイン
- 投稿画面メタボックス「パーマリンク推奨」：「候補を生成」→ 候補カード → 「適用」（提案型・自動書き込みなし）。
- **表示・実行・保存フックをすべて `edit_others_posts` 権限に統一**（管理者・編集者のみ。投稿者・寄稿者は非表示）。
- REST `POST /wp-json/auto-permanent-link/v1/suggest`：`X-WP-Nonce` 検証 + 権限チェック後に Lambda へプロキシ。
- **slug は保存時にサーバー側で確定**：隠しフィールド `apl_selected_slug` に選択値を保持し、
  `wp_insert_post_data` フック（`class-apl-save.php`）で nonce + 権限を検証して `post_name` を強制。
  フロントはコア JS と競合しない（「一瞬入って戻る」問題を根治）。Classic / Gutenberg 両対応。

### 検証
- `aws/tests/`：slug 正規化テスト + 認証テスト（`lambda_handler` を合成イベントで直接検証、401/503/200/400/health）。
- 実機で「候補を生成 → 適用 → 保存」後、パーマリンクが選んだ英語 slug に確定することを確認。
