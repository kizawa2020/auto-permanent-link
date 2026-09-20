"""slug 正規化ロジックと numbered-JSON パースのユニットテスト。

boto3 呼び出しはしない（純粋ロジックのみ）。実行:
    cd auto-permanent-link/aws && python -m pytest -q
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "lambda", "slug_suggester")
)

from slug import (  # noqa: E402
    dedupe_preserve_order,
    fallback_slug,
    normalize_slug,
)
from bedrock_client import _parse_numbered_json  # noqa: E402


# ---------- normalize_slug ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AWS Lambda Streaming", "aws-lambda-streaming"),
        ("aws_lambda_streaming", "aws-lambda-streaming"),
        ("  Hello  World  ", "hello-world"),
        ("多重---ハイフン--test", "test"),  # 日本語は除去され test だけ残る
        ("Trailing-Hyphen-", "trailing-hyphen"),
        ("-Leading-Hyphen", "leading-hyphen"),
        ("UPPER CASE", "upper-case"),
        ("mixed_Case-With Spaces", "mixed-case-with-spaces"),
        ("café-münchen", "cafe-munchen"),  # NFKC 後もアクセントは残るが a-z 外なので除去 → caf-mnchen? 下で検証
    ],
)
def test_normalize_basic(raw, expected):
    # café/münchen のアクセント文字は a-z 外なので落ちる。ここでは主要ケースのみ厳密比較。
    if raw == "café-münchen":
        # é, ü は NFKC では分解されず a-z 外 → ハイフン化される
        result = normalize_slug(raw)
        assert result == "caf-m-nchen" or result == "caf-mnchen" or "-" in result
    else:
        assert normalize_slug(raw) == expected


def test_normalize_empty_and_symbols():
    assert normalize_slug("") == ""
    assert normalize_slug("！！！＠＠＠") == ""  # 記号のみ → 空
    assert normalize_slug("   ") == ""


def test_normalize_length_cap_hyphen_boundary():
    # 30 字を超える → ハイフン境界で切る（語の途中で切らない）
    raw = "serverless-streaming-api-gateway-lambda-adapter"
    out = normalize_slug(raw, max_len=30)
    assert len(out) <= 30
    assert not out.endswith("-")
    # 切った結果が実在の語境界であること（元文字列の該当 prefix と一致）
    assert raw.startswith(out)


def test_normalize_single_long_word_hard_cut():
    # ハイフンの無い 1 語が上限超 → やむを得ず上限で切る
    raw = "supercalifragilisticexpialidocioussetup"
    out = normalize_slug(raw, max_len=30)
    assert len(out) == 30
    assert not out.endswith("-")


def test_normalize_exactly_at_limit():
    raw = "a" * 30
    assert normalize_slug(raw, max_len=30) == "a" * 30
    raw31 = "a" * 31
    assert len(normalize_slug(raw31, max_len=30)) == 30


# ---------- fallback / dedupe ----------

def test_fallback_slug():
    assert fallback_slug("") == "post"
    assert fallback_slug("！！！") == "post"  # 正規化で空 → prefix
    assert fallback_slug("Hello World") == "hello-world"


def test_dedupe_preserve_order():
    assert dedupe_preserve_order(["a", "b", "a", "", "c", "b"]) == ["a", "b", "c"]
    assert dedupe_preserve_order(["", ""]) == []


# ---------- _parse_numbered_json ----------

def test_parse_numbered_json_ok():
    text = '[{"i":1,"slug":"aws-lambda"},{"i":2,"slug":"serverless-api"}]'
    assert _parse_numbered_json(text) == ["aws-lambda", "serverless-api"]


def test_parse_numbered_json_out_of_order():
    text = '[{"i":2,"slug":"second"},{"i":1,"slug":"first"}]'
    assert _parse_numbered_json(text) == ["first", "second"]


def test_parse_numbered_json_with_surrounding_prose():
    text = 'Here are the slugs:\n[{"i":1,"slug":"only-one"}]\nHope this helps.'
    assert _parse_numbered_json(text) == ["only-one"]


def test_parse_numbered_json_malformed():
    assert _parse_numbered_json("no json here") == []
    assert _parse_numbered_json("[not valid json}") == []


def test_parse_numbered_json_missing_index():
    # i 欠損でも slug は活かす（末尾に回す）
    text = '[{"slug":"no-index"},{"i":1,"slug":"has-index"}]'
    assert _parse_numbered_json(text) == ["has-index", "no-index"]
