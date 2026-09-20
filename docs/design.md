# auto-permanent-link — 設計仕様書

WordPress 記事のパーマリンク（slug）を、記事タイトルから AI で英語スラッグとして推奨するシステム。
記事投稿画面のボタン押下で、オンデマンドに推奨候補を表示する。

---

## 1. スコープと方針

- **完全分離の独立実装**。既存プロジェクトと
  CloudFront / WAF / 認証 / Lambda / VectorDB を一切共有しない。専用の CloudFormation スタックを持つ。
- 共有するのは Bedrock Nova（マネージド API を各自が独立して呼ぶ）のみ。
- **英語スラッグ**を生成する。**概ね 30 文字以内**。ハイフン区切り。
- **オンデマンド同期**：投稿画面の「slug 推奨」ボタン押下で 1 回実行 → 候補を表示 → ユーザーが選んで
  パーマリンク欄へ反映。**自動書き込みはしない（提案型）**。

## 2. アーキテクチャ

```
[WordPress 投稿編集画面]
   └ メタボックス「パーマリンク推奨」ボタン
        │ (管理画面 REST, X-WP-Nonce + edit_others_posts 権限チェック)
        ▼
   [WordPress プラグイン auto-permanent-link]
        │ HTTPS POST { title, excerpt? }
        ▼
   [API Gateway]  ── 独立スタック（WAF なし・VectorDB なし）
        ▼
   [Lambda (素のハンドラ / Python 3.12)]
        │ Bedrock Converse
        ▼
   [Bedrock Nova 2 Lite]  → 英語 slug 候補 2〜3 案（JSON）
        ▲
   正規化（英小文字・ハイフン化・30字以内・重複ハイフン除去）
```

- ランタイム：Python 3.12 / 素の Lambda ハンドラ（`app.lambda_handler`、API Gateway REST プロキシ統合）。
  外部依存は boto3（ランタイム同梱）のみで、FastAPI/uvicorn/Lambda Web Adapter は使わない。
- モデル：`jp.amazon.nova-2-lite-v1:0`（クロスリージョン推論プロファイル。既存 chat と同一モデル、呼び出しは独立）。環境変数 `MODEL_ID` で変更可。
- 認証：WordPress 管理画面の **nonce**（`X-WP-Nonce` / `wp_rest`）＋ **`current_user_can('edit_others_posts')`** 権限チェック。
  管理者・編集者のみ利用可能（投稿者・寄稿者は不可）。加えて Lambda 側で共有シークレット `X-Api-Secret` を定数時間比較(A)、API Gateway で APIキー+Usage Plan(B)。chat の HMAC トークンとは別方式。
- WAF なし（管理者限定・低頻度アクセスのため）。VectorDB / Titan Embeddings なし。

## 3. slug 生成仕様

### 入力
- `title`（必須）：記事タイトル。日本語想定。
- `excerpt`（任意）：本文冒頭 200〜300 文字程度。タイトルだけで文脈が薄い場合の精度向上用。

### Nova プロンプト方針
- システムプロンプトで役割を固定：「WordPress 記事の URL スラッグを生成する。英語・小文字・ハイフン区切り・
  簡潔・記事内容を表す語のみ」。
- 出力は **numbered JSON**（`[{"i":1,"slug":"..."}, ...]`）で 3 案。index マッピングで受け取る
  （区切り文字方式は使わない — 過去のバッチ翻訳の教訓に準拠）。
- 温度は低め（0.2 前後）で安定した語選択。環境変数 `GENERATION_TEMPERATURE` で調整可能に。

### 正規化（Lambda 側で確定処理。モデル出力を信頼しすぎない）
1. Unicode NFKC 正規化 → 英小文字化。
2. 英数字とハイフン以外を削除、空白・アンダースコアはハイフンへ。
3. 連続ハイフンを 1 個に、先頭末尾のハイフンを除去。
4. **30 文字以内**に切り詰め。切り詰めで語の途中になる場合は最後の完全な語（ハイフン境界）で切る。
5. 空文字になった場合はフォールバック（`post` + タイムスタンプ等）。
- 30 字は「概ね」の上限。ハイフン境界優先で 30 字を少しだけ超えない範囲に収める。

### 出力
```json
{
  "suggestions": [
    { "slug": "aws-lambda-streaming", "length": 20 },
    { "slug": "lambda-web-adapter-setup", "length": 24 },
    { "slug": "serverless-streaming-api", "length": 24 }
  ]
}
```
- 重複除去済み・正規化済みの候補のみ返す。最大 3 案。

## 4. WordPress プラグイン仕様

- プラグイン名：`auto-permanent-link`（Classic エディタ想定、Gutenberg でも動作を目指す）。
- 投稿編集画面に **メタボックス**「パーマリンク推奨」を追加。
- ボタン「候補を生成」押下 → 現在のタイトル（＋任意で本文冒頭）を AJAX/REST で送信 → 候補カード表示。
- 各候補に「この slug を適用」ボタン → WordPress の slug 入力欄（`#new-post-slug` / `#post_name`）へ反映。
- nonce 検証と `edit_others_posts` 権限チェックを PHP ハンドラ（REST）で実施。表示・実行・保存フックを同一境界に統一。
- slug は保存時に `wp_insert_post_data` フックでサーバー側確定（フロントはコア JS と競合しない）。
- Lambda エンドポイント URL は設定画面で入力（オプションページ）。

## 5. ディレクトリ構成

```
auto-permanent-link/
├── docs/
│   └── design.md                      ← 本ファイル
├── aws/
│   ├── lambda/slug_suggester/
│   │   ├── app.py                     ← Lambda ハンドラ（lambda_handler）
│   │   ├── slug.py                    ← 正規化ロジック（純関数・テスト対象）
│   │   ├── bedrock_client.py          ← Nova 呼び出し
│   │   └── requirements.txt
│   ├── tests/
│   │   └── test_slug.py               ← 正規化ロジックのユニットテスト
│   ├── template.yaml                  ← CloudFormation（Lambda + API GW、WAF なし）
│   └── README.md
├── wordpress/auto-permanent-link/
│   ├── auto-permanent-link.php        ← プラグイン本体
│   ├── includes/                      ← メタボックス・AJAX ハンドラ・設定ページ
│   └── assets/js, assets/css          ← フロント（候補表示・適用）
└── README.md
```

## 6. コスト

- 1 回の推奨 ≈ 入力数百 + 出力数十トークン程度で ¥0.1 未満／回。
- 管理者が投稿時に押す低頻度用途のため月額は数十円レベル。WAF・VectorDB なしで固定費最小。

## 7. 非スコープ

- 既存記事の一括 slug 付け替え（バッチ）は対象外（将来拡張）。
- 重複 slug の WordPress 側自動サフィックス（`-2` 等）は WordPress 標準挙動に委ねる。
- fact-check / 本文全文の RAG は対象外（依存なし）。

## 8. 運用

- ビルド／デプロイ／S3 アップロードはポリシー上ユーザーが実施（既存プロジェクトと同運用）。
  本リポジトリはコード・テンプレート・プラグイン一式を用意するところまで。
