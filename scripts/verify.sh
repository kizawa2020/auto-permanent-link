#!/usr/bin/env bash
# auto-permanent-link 検証スクリプト。
# - PHP CLI があればプラグインの全 .php を php -l で構文チェック
# - Python venv を用意してバックエンドの pytest を実行
#
# 使い方: ./scripts/verify.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== PHP syntax check =="
if command -v php >/dev/null 2>&1; then
  fail=0
  while IFS= read -r f; do
    php -l "$f" || fail=1
  done < <(find "$ROOT/wordpress" -name '*.php')
  [ "$fail" -eq 0 ] && echo "PHP: all files OK" || { echo "PHP: syntax errors found"; exit 1; }
else
  echo "PHP CLI not found — skipping php -l (install php-cli to enable)."
fi

echo
echo "== Python backend tests =="
VENV="${APL_VENV:-$ROOT/.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q pytest boto3 fastapi httpx pydantic
fi
cd "$ROOT/aws"
"$VENV/bin/python" -m pytest -q tests/

echo
echo "All checks passed."
