"""app.py — 素の Lambda ハンドラ（API Gateway REST プロキシ統合 / payload v1.0）。

FastAPI / uvicorn / Lambda Web Adapter は使わない。標準ライブラリ + boto3(ランタイム同梱)のみ。

ルーティング（event.httpMethod + event.path / resource）:
  GET  /health   → {"status": "ok"}（認証不要・ヘルスチェック用）
  POST /suggest  → 共有シークレット必須
    header: X-Api-Secret: <SHARED_SECRET>
    body:  {"title": str, "excerpt": str?, "exclude": [str], "variety": bool}
    resp:  {"suggestions": [{"slug": str, "length": int}, ...]}（最大 NUM_SUGGESTIONS 案）
  OPTIONS *       → CORS プリフライト 200（API GW 側の OPTIONS(MOCK) が主だが保険で対応）

セキュリティ二段構え:
  (A) 共有シークレットヘッダー: X-Api-Secret を環境変数 SHARED_SECRET と定数時間比較。
      未設定なら 503（ノーガード公開を防ぐ安全側フェイル）、不一致/欠損は 401。
  (B) レート制限: API Gateway の APIキー + Usage Plan（template.yaml 側）。
"""

from __future__ import annotations

import hmac
import json
import logging
import os

from bedrock_client import MAX_SLUG_LEN, NUM_SUGGESTIONS, suggest_slugs
from slug import dedupe_preserve_order, fallback_slug, normalize_slug

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 許可オリジン（カンマ区切り）。本番は WordPress サイトのオリジンに絞る。
_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
_ALLOW_ORIGIN = _ORIGINS[0] if len(_ORIGINS) == 1 else "*"

# (A) 共有シークレット。未設定なら /suggest は全て 503。
SHARED_SECRET = os.environ.get("SHARED_SECRET", "")
if not SHARED_SECRET:
    logger.warning(
        "SHARED_SECRET is not set — /suggest will refuse all requests until it is configured."
    )

MAX_TITLE_LEN = 300
MAX_EXCERPT_LEN = 2000
MAX_EXCLUDE = 50


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": _ALLOW_ORIGIN,
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Requested-With,X-Api-Secret,x-api-key",
    }


def _resp(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **_cors_headers()},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _get_header(headers: dict, name: str) -> str:
    """ヘッダは大文字小文字が揺れるので case-insensitive に取る。"""
    if not headers:
        return ""
    lname = name.lower()
    for k, v in headers.items():
        if k.lower() == lname:
            return v or ""
    return ""


def _check_secret(headers: dict):
    """(A) X-Api-Secret を定数時間比較。OK なら None、NG なら error レスポンス dict。"""
    if not SHARED_SECRET:
        return _resp(503, {"message": "server not configured"})
    supplied = _get_header(headers, "X-Api-Secret")
    if not hmac.compare_digest(supplied, SHARED_SECRET):
        return _resp(401, {"message": "invalid or missing secret"})
    return None


def _handle_suggest(body: dict) -> dict:
    title = str(body.get("title", "")).strip()
    if not title:
        return _resp(400, {"message": "title is required"})
    title = title[:MAX_TITLE_LEN]

    excerpt = body.get("excerpt")
    if excerpt is not None:
        excerpt = str(excerpt).strip()[:MAX_EXCERPT_LEN] or None

    exclude_in = body.get("exclude") or []
    if not isinstance(exclude_in, list):
        exclude_in = []
    variety = bool(body.get("variety", False))

    # 除外集合は正規化して比較（表記ゆれ吸収）。
    exclude_set = {
        normalize_slug(str(s), MAX_SLUG_LEN) for s in exclude_in[:MAX_EXCLUDE] if s
    }
    exclude_set.discard("")

    raw_candidates = suggest_slugs(
        title, excerpt, exclude=list(exclude_set), variety=variety
    )

    normalized = [normalize_slug(c, MAX_SLUG_LEN) for c in raw_candidates]
    normalized = dedupe_preserve_order(normalized)

    # 既出候補を最終結果からも除外（モデルが従わなかった場合の保険）。
    if exclude_set:
        filtered = [s for s in normalized if s not in exclude_set]
        normalized = filtered or normalized  # 全除外なら空応答を避けて従来案

    # 何も返せなければタイトルからフォールバックを1件。
    if not normalized:
        normalized = [fallback_slug(title)]

    normalized = normalized[:NUM_SUGGESTIONS]
    return _resp(
        200,
        {"suggestions": [{"slug": s, "length": len(s)} for s in normalized]},
    )


def lambda_handler(event: dict, context) -> dict:
    """API Gateway REST プロキシ統合(payload v1.0)のエントリ。"""
    method = (event.get("httpMethod") or "").upper()
    # resource（例 /suggest）優先、無ければ path。
    route = event.get("resource") or event.get("path") or ""

    # CORS プリフライト（API GW 側 OPTIONS(MOCK) が本筋だが保険で 200 を返す）。
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    if route.endswith("/health") and method == "GET":
        return _resp(200, {"status": "ok"})

    if route.endswith("/suggest") and method == "POST":
        # (A) シークレット検証
        err = _check_secret(event.get("headers") or {})
        if err is not None:
            return err
        # body パース
        raw = event.get("body") or ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return _resp(400, {"message": "invalid JSON body"})
        if not isinstance(body, dict):
            return _resp(400, {"message": "invalid JSON body"})
        try:
            return _handle_suggest(body)
        except Exception:  # noqa: BLE001 — 予期せぬ失敗も 500 の JSON で返す（502 化させない）
            logger.exception("suggest failed")
            return _resp(500, {"message": "internal error"})

    return _resp(404, {"message": "not found"})
