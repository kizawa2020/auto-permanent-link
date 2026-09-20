"""slug.py — 英語スラッグの正規化ロジック（純関数・依存なし）。

正規化仕様（docs/design.md §3）:
  1. NFKC 正規化 → 英小文字化
  2. 英数字・ハイフン以外を削除、空白/アンダースコアはハイフンへ
  3. 連続ハイフンを 1 個に、先頭末尾ハイフン除去
  4. 30 文字以内に切り詰め（ハイフン境界優先。1語で超える場合のみ語中で切る）
  5. 空になったらフォールバック

このモジュールは boto3 等に依存しないため、AWS 環境なしでユニットテストできる。
"""

from __future__ import annotations

import re
import unicodedata

MAX_LEN = 30
FALLBACK_PREFIX = "post"

_NON_SLUG = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN = re.compile(r"-{2,}")


def normalize_slug(raw: str, max_len: int = MAX_LEN) -> str:
    """モデル出力の生スラッグを URL-safe な英小文字ハイフン区切りへ正規化する。

    空文字になった場合は "" を返す（呼び出し側でフォールバックを選択できるように）。
    フォールバック文字列そのものが必要なときは fallback_slug() を使う。
    """
    if not raw:
        return ""

    # 1. NFKC 正規化（全角→半角など）→ 英小文字化
    s = unicodedata.normalize("NFKC", raw).lower()

    # 2. 空白・アンダースコアをハイフンへ、英数字とハイフン以外を除去
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    s = _NON_SLUG.sub("-", s)

    # 3. 連続ハイフンを 1 個に、先頭末尾ハイフン除去
    s = _MULTI_HYPHEN.sub("-", s).strip("-")

    if not s:
        return ""

    # 4. 30 文字以内に切り詰め（ハイフン境界優先）
    s = _truncate_on_hyphen(s, max_len)

    return s


def _truncate_on_hyphen(s: str, max_len: int) -> str:
    """max_len 以内に収める。可能ならハイフン境界で切り、単語の途中で切らない。

    1 語目だけで max_len を超える場合は、やむを得ず max_len で切る。
    """
    if len(s) <= max_len:
        return s

    # max_len 位置までの範囲で最後のハイフンを探す
    head = s[:max_len]
    cut = head.rfind("-")
    if cut > 0:
        # ハイフン境界で切って末尾ハイフンを除去
        return head[:cut].rstrip("-")
    # 1 語で超過 → max_len でハード切り（末尾ハイフンは念のため除去）
    return head.rstrip("-")


def fallback_slug(seed: str = "") -> str:
    """正規化結果が空のときに使う安全なフォールバック slug。

    seed から作れなければ prefix のみを返す（WordPress 側で -2 等が付与される想定）。
    """
    s = normalize_slug(seed) if seed else ""
    return s or FALLBACK_PREFIX


def dedupe_preserve_order(slugs: list[str]) -> list[str]:
    """重複を除きつつ順序を保つ。空文字は除外する。"""
    seen: set[str] = set()
    out: list[str] = []
    for slug in slugs:
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out
