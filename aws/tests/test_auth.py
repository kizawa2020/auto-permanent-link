"""(A) 共有シークレット照合のテスト。

素の Lambda ハンドラ(app.lambda_handler)を、API Gateway REST プロキシ統合(payload v1.0)
相当のイベントで直接呼び、/suggest の 401/503/200 と /health を検証する。
Bedrock 呼び出しは suggest_slugs をモックして外部依存を切る。

実行:
    cd auto-permanent-link/aws && python -m pytest -q tests/test_auth.py
"""

import importlib
import json
import os
import sys

_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "lambda", "slug_suggester")
sys.path.insert(0, _APP_DIR)


def _load_app(monkeypatch, secret: str | None):
    """SHARED_SECRET を設定/未設定にして app モジュールを読み直す。"""
    if secret is None:
        monkeypatch.delenv("SHARED_SECRET", raising=False)
    else:
        monkeypatch.setenv("SHARED_SECRET", secret)
    import app as app_module

    importlib.reload(app_module)
    # Bedrock を叩かないようモック（正規化経路だけ検証）
    monkeypatch.setattr(
        app_module,
        "suggest_slugs",
        lambda title, excerpt=None, exclude=None, variety=False: ["aws-lambda"],
    )
    return app_module


def _suggest_event(body: dict, secret: str | None):
    headers = {}
    if secret is not None:
        headers["X-Api-Secret"] = secret
    return {
        "httpMethod": "POST",
        "resource": "/suggest",
        "path": "/suggest",
        "headers": headers,
        "body": json.dumps(body),
    }


def _call(app_module, event):
    resp = app_module.lambda_handler(event, None)
    body = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], body


def test_missing_secret_returns_401(monkeypatch):
    app_module = _load_app(monkeypatch, secret="a-very-long-shared-secret")
    status, _ = _call(app_module, _suggest_event({"title": "AWS Lambda 入門"}, secret=None))
    assert status == 401


def test_wrong_secret_returns_401(monkeypatch):
    app_module = _load_app(monkeypatch, secret="a-very-long-shared-secret")
    status, _ = _call(app_module, _suggest_event({"title": "AWS Lambda 入門"}, secret="wrong"))
    assert status == 401


def test_correct_secret_returns_200(monkeypatch):
    secret = "a-very-long-shared-secret"
    app_module = _load_app(monkeypatch, secret=secret)
    status, body = _call(app_module, _suggest_event({"title": "AWS Lambda 入門"}, secret=secret))
    assert status == 200
    assert body["suggestions"][0]["slug"] == "aws-lambda"


def test_unconfigured_secret_returns_503(monkeypatch):
    # サーバー側で SHARED_SECRET 未設定 → ノーガード公開ではなく 503 で拒否
    app_module = _load_app(monkeypatch, secret=None)
    status, _ = _call(app_module, _suggest_event({"title": "AWS Lambda 入門"}, secret="anything"))
    assert status == 503


def test_missing_title_returns_400(monkeypatch):
    secret = "a-very-long-shared-secret"
    app_module = _load_app(monkeypatch, secret=secret)
    status, _ = _call(app_module, _suggest_event({}, secret=secret))
    assert status == 400


def test_health_needs_no_secret(monkeypatch):
    app_module = _load_app(monkeypatch, secret="a-very-long-shared-secret")
    status, body = _call(
        app_module,
        {"httpMethod": "GET", "resource": "/health", "path": "/health", "headers": {}, "body": ""},
    )
    assert status == 200
    assert body == {"status": "ok"}
