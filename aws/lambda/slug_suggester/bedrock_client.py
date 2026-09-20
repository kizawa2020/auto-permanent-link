"""bedrock_client.py — Bedrock Nova 2 Lite で英語 slug 候補を生成する。

- モデル: jp.amazon.nova-2-lite-v1:0（クロスリージョン推論プロファイル）
- Converse API を使用
- 出力は numbered JSON ([{"i":1,"slug":"..."}...]) で受け取り index でマッピング
  （区切り文字方式は使わない — count-mismatch を避けるため）
- 温度は GENERATION_TEMPERATURE 環境変数（既定 0.2）
"""

from __future__ import annotations

import json
import logging
import os
import re

import boto3

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "jp.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
GENERATION_TEMPERATURE = float(os.environ.get("GENERATION_TEMPERATURE", "0.2"))
NUM_SUGGESTIONS = int(os.environ.get("NUM_SUGGESTIONS", "3"))
MAX_SLUG_LEN = int(os.environ.get("MAX_SLUG_LEN", "30"))
EXCERPT_MAX_CHARS = int(os.environ.get("EXCERPT_MAX_CHARS", "300"))

_SYSTEM_PROMPT = (
    "You generate URL slugs for WordPress blog articles about IT and cloud technology. "
    "Rules for every slug you produce:\n"
    "- English only, lowercase, words separated by single hyphens.\n"
    f"- Concise: aim for at most {MAX_SLUG_LEN} characters. Prefer 2-4 meaningful words.\n"
    "- Describe the article's core topic; drop filler words (the, a, how, guide) unless essential.\n"
    "- No spaces, no underscores, no punctuation other than hyphens, no trailing hyphen.\n"
    "- Translate/summarize a Japanese title into natural English keywords, do not transliterate kana.\n"
    "Return ONLY a JSON array, no prose, in the exact form: "
    '[{"i":1,"slug":"..."},{"i":2,"slug":"..."},{"i":3,"slug":"..."}]'
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def _client():
    return boto3.client("bedrock-runtime", region_name=REGION)


def _build_user_message(
    title: str, excerpt: str | None, exclude: list[str] | None = None
) -> str:
    parts = [f"Article title (may be Japanese): {title.strip()}"]
    if excerpt:
        clipped = excerpt.strip()[:EXCERPT_MAX_CHARS]
        if clipped:
            parts.append(f"Article opening (for context): {clipped}")
    if exclude:
        # 直前に提示済みの候補を伝え、それとは異なる新しい案を要求する。
        shown = ", ".join(exclude[:20])
        parts.append(
            "Do NOT repeat any of these already-suggested slugs; produce different, "
            f"fresh alternatives (new wording, synonyms, different word order): {shown}"
        )
    parts.append(
        f"Produce {NUM_SUGGESTIONS} distinct English slug candidates as the JSON array described."
    )
    return "\n".join(parts)


def _parse_numbered_json(text: str) -> list[str]:
    """モデル出力から numbered JSON を取り出し、i でソートして slug のリストを返す。"""
    m = _JSON_ARRAY.search(text)
    if not m:
        logger.warning("No JSON array found in model output: %r", text[:200])
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON array: %r", m.group(0)[:200])
        return []

    items = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        i = obj.get("i")
        slug = obj.get("slug")
        if slug is None:
            continue
        # i が欠損/不正でも slug は活かす（順序末尾に回す）
        order = i if isinstance(i, int) else 10_000
        items.append((order, str(slug)))
    items.sort(key=lambda t: t[0])
    return [slug for _, slug in items]


def suggest_slugs(
    title: str,
    excerpt: str | None = None,
    exclude: list[str] | None = None,
    variety: bool = False,
) -> list[str]:
    """Nova を呼び出し、正規化前の英語 slug 候補（生文字列）を返す。

    - exclude: 既に提示済みの slug。プロンプトで「これ以外」を要求する（再生成の多様化）。
    - variety: True のとき温度を上げて出力をばらけさせる（「もう一度」で別候補を出す用途）。
    呼び出し失敗や空応答時は空リストを返す（呼び出し側でフォールバック）。
    """
    user_msg = _build_user_message(title, excerpt, exclude)
    # 再生成時は温度を上げて多様性を出す（上限 1.0）。
    temperature = min(1.0, GENERATION_TEMPERATURE + 0.5) if variety else GENERATION_TEMPERATURE
    try:
        resp = _client().converse(
            modelId=MODEL_ID,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_msg}]}],
            inferenceConfig={
                "temperature": temperature,
                "maxTokens": 300,
            },
        )
    except Exception:  # noqa: BLE001 — ここは握って空返し、呼び出し側でフォールバック
        logger.exception("Bedrock converse call failed")
        return []

    try:
        text = resp["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected Bedrock response shape: %r", resp)
        return []

    return _parse_numbered_json(text)
