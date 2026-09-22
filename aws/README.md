# auto-permanent-link — AWS バックエンド

英語スラッグ推奨 API。API Gateway + Lambda(素のハンドラ / Python 3.12) + Bedrock Nova 2 Lite。
WAF なし・VectorDB なしの独立スタック。

## エンドポイント

- `GET  /health`  → `{"status":"ok"}`
- `POST /suggest`
  - req: `{"title": "記事タイトル", "excerpt": "本文冒頭(任意)"}`
  - resp: `{"suggestions": [{"slug":"aws-lambda-streaming","length":20}, ...]}`（最大3案）

## セキュリティ（二段構え）

管理者限定・低頻度の独立エンドポイントを、WordPress の nonce/権限チェック（呼び出し元側）に加えて
API Gateway レベルでも守る。

- **(A) 共有シークレットヘッダー**：プラグインが `X-Api-Secret: <SharedSecret>` を送り、Lambda が
  環境変数 `SHARED_SECRET` と **定数時間比較**（`hmac.compare_digest`）。不一致/欠損は `401`。
  サーバー側で `SHARED_SECRET` 未設定なら `/suggest` は `503`（ノーガード公開を防ぐ安全側フェイル）。
- **(B) API Gateway APIキー + Usage Plan**：`/suggest` は `x-api-key` 必須。Usage Plan で
  レート制限（既定 5 req/s, burst 10）と **日次クォータ**（既定 500 req/day）を課し、コスト暴走を上限化。
- `/health` は認証不要（死活監視用）。
- CORS はブラウザ制限のみ（サーバー間呼び出しには無力なので、認証は上記 A/B で担保）。

APIキー値の取得（デプロイ後）:

```bash
# スタック Outputs の ApiKeyId を取得
KEY_ID=$(aws cloudformation describe-stacks --stack-name auto-permanent-link \
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeyId'].OutputValue" --output text)
# その ID から実際のキー値を取り出す
aws apigateway get-api-key --api-key "$KEY_ID" --include-value \
  --query value --output text
```

取得した `x-api-key` と、デプロイ時に指定した `SharedSecret` をプラグイン設定に登録する。

## slug 生成の流れ

1. Nova 2 Lite に title(＋excerpt) を渡し、numbered JSON `[{"i":1,"slug":"..."}]` で英語候補を取得
2. Lambda 側で正規化（`slug.normalize_slug`）: NFKC→英小文字→ハイフン化→**30字以内（ハイフン境界優先）**→重複除去
3. 全滅時はタイトルからフォールバック slug を1件生成

モデル出力を信頼しすぎず、長さ・文字種の保証は必ず Lambda 側の正規化で担保する。

## ユニットテスト

```bash
cd aws
python -m venv .venv && . .venv/bin/activate
pip install pytest boto3
python -m pytest -q tests/test_slug.py
```

正規化ロジック（`slug.py`）と numbered-JSON パース（`bedrock_client._parse_numbered_json`）を
Bedrock 呼び出しなしで検証する。

## ビルド & デプロイ（ユーザー実施）

素の CloudFormation（SAM ではない）。Lambda コードは **S3 に置いて参照**する方式。

```bash
cd aws

# 0) 一度だけ: コード配置用の S3 バケットを用意（既存バケットでも可）
BUCKET=auto-permanent-link-code-<accountid>   # 任意の一意な名前
aws s3 mb s3://$BUCKET

# 1) Lambda コードを zip 化（依存ゼロ: 素のハンドラで boto3 のみ＝ランタイム同梱、.py のみ）
( cd lambda/slug_suggester && zip -r -X /tmp/slug_suggester.zip . -x '*__pycache__*' -x 'build/*' -x '*.pyc' -x 'requirements.txt' )

# 2) S3 へアップロード
aws s3 cp /tmp/slug_suggester.zip s3://$BUCKET/slug_suggester.zip

# 3) スタック作成/更新
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name auto-permanent-link \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      CodeBucket=$BUCKET \
      CodeKey=slug_suggester.zip \
      SharedSecret=<16文字以上のランダム値> \
      AllowedOrigins=https://example.com
```

### コードだけ更新するとき（テンプレート変更なし）

S3 キーが固定（`slug_suggester.zip`）のため `cloudformation deploy` はコード変更を検知しない。
コードのみの反映は `lambda update-function-code` を使う:

```bash
( cd lambda/slug_suggester && zip -r -X /tmp/slug_suggester.zip . -x '*__pycache__*' -x 'build/*' -x '*.pyc' -x 'requirements.txt' )
aws s3 cp /tmp/slug_suggester.zip s3://$BUCKET/slug_suggester.zip
aws lambda update-function-code \
  --function-name auto-permanent-link-slug-suggester \
  --s3-bucket $BUCKET --s3-key slug_suggester.zip
```

- `CAPABILITY_NAMED_IAM` が必要（IAM ロールを名前付きで作成するため）。
- ハンドラは `app.lambda_handler`（素の Lambda ハンドラ）。FastAPI/uvicorn/Lambda Web Adapter は不要。
- デプロイ後、Outputs の `ApiEndpoint` に `/suggest` を付けた URL を WordPress プラグイン設定へ登録。
- 本番では `AllowedOrigins` を WordPress サイトのオリジンに絞る。

## 環境変数

| 変数 | 既定 | 説明 |
|------|------|------|
| `MODEL_ID` | `jp.amazon.nova-2-lite-v1:0` | Bedrock モデル/推論プロファイル |
| `BEDROCK_REGION` | `ap-northeast-1` | Bedrock ランタイム呼び出しリージョン |
| `GENERATION_TEMPERATURE` | `0.2` | 生成温度 |
| `MAX_SLUG_LEN` | `30` | slug 最大長 |
| `NUM_SUGGESTIONS` | `3` | 返す候補数 |
| `ALLOWED_ORIGINS` | `*` | CORS 許可オリジン（カンマ区切り） |
| `SHARED_SECRET` | （必須・NoEcho） | (A) `X-Api-Secret` と定数時間比較する共有シークレット。未設定だと `/suggest` は 503 |

## デプロイ時パラメータ

`cloudformation deploy --parameter-overrides` で指定する:

| パラメータ | 既定 | 説明 |
|-----------|------|------|
| `CodeBucket` | （必須） | Lambda zip を置く S3 バケット名 |
| `CodeKey` | `slug_suggester.zip` | Lambda zip の S3 キー |
| `SharedSecret` | （必須・16字以上・NoEcho） | (A) プラグインと共有する秘密文字列 |
| `AllowedOrigins` | `*` | CORS 許可オリジン（本番はサイトオリジンに絞る） |
| `RateLimitPerSecond` | `5` | (B) 定常レート（req/s） |
| `RateBurst` | `10` | (B) バースト上限 |
| `DailyQuota` | `500` | (B) 日次リクエスト上限（コスト暴走の上限） |
