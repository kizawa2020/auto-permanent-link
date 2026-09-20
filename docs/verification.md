# 動作確認手順（E2E）

デプロイ後にバックエンドとプラグインを通しで確認する手順。

## 0. 自動チェック（ローカル）

```bash
./scripts/verify.sh
```

- PHP CLI があればプラグイン全 `.php` を `php -l` で構文チェック
- バックエンドの pytest（正規化20 + 認証5 = 25件）を実行

## 1. バックエンド単体（curl）

デプロイ後、`ApiEndpoint` と `SharedSecret`・`x-api-key` を控える。

```bash
API="https://xxxx.execute-api.ap-northeast-1.amazonaws.com/prod"
SECRET="＜SharedSecret＞"
APIKEY="＜x-api-key＞"

# health（認証不要）
curl -s "$API/health"
# => {"status":"ok"}

# 正常系: 英語スラッグ候補が最大3件、各 length<=30
curl -s -X POST "$API/suggest" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $APIKEY" \
  -H "X-Api-Secret: $SECRET" \
  -d '{"title":"AWS Lambda のレスポンスストリーミング設定入門"}' | python3 -m json.tool
# => {"suggestions":[{"slug":"aws-lambda-streaming", "length":20}, ...]}
```

### セキュリティ確認（拒否されること）

```bash
# (A) シークレット無し/誤り → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/suggest" \
  -H "Content-Type: application/json" -H "x-api-key: $APIKEY" \
  -d '{"title":"test"}'
# => 401

# (B) APIキー無し → 403 (Forbidden, API Gateway が弾く)
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/suggest" \
  -H "Content-Type: application/json" -H "X-Api-Secret: $SECRET" \
  -d '{"title":"test"}'
# => 403

# (B) レート/クォータ超過 → 429 (Too Many Requests) を Usage Plan が返す
```

## 2. プラグイン（WordPress 管理画面）

1. プラグイン有効化 → 「設定 → Auto Permanent Link」で URL / シークレット / APIキーを保存。
2. 投稿を新規作成し、タイトルを入力（例: 「New Relic で作る運用監視ダッシュボード」）。
3. 右サイド「パーマリンク推奨」→「候補を生成」。
4. 英語スラッグ候補が最大3件・各30字以内で表示されること。
5. 「適用」でパーマリンク（slug）欄へ反映されること（Classic / Gutenberg 両方）。
6. 権限のないユーザー（購読者など）ではボタン経由の呼び出しが 401/403 になること。

## 3. 期待される不変条件（正規化）

- slug は英小文字・数字・ハイフンのみ
- 30 文字以内（ハイフン境界優先で切断、単語途中では極力切らない）
- 先頭/末尾ハイフンなし、連続ハイフンなし
- 日本語のみのタイトルは英語要約 slug（不能時は `post` フォールバック）

これらは `aws/tests/test_slug.py` で自動検証済み。
