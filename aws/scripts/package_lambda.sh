#!/usr/bin/env bash
#
# package_lambda.sh — Lambda デプロイ用 zip を作る。
#
# 素の Lambda ハンドラ方式(app.lambda_handler)のため、外部依存は boto3 のみで、
# それは Lambda ランタイム(python3.12)に同梱される。したがって zip にはソース .py
# だけを入れればよく、pip install は不要（FastAPI/uvicorn/LWA を撤去済み）。
#
# 使い方:
#   bash scripts/package_lambda.sh            # /tmp/slug_suggester.zip を生成
#   OUT=/path/to.zip bash scripts/package_lambda.sh   # 出力先を変える

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/../lambda/slug_suggester" && pwd)"
OUT="${OUT:-/tmp/slug_suggester.zip}"

echo "== source: $SRC_DIR"
echo "== output: $OUT"

rm -f "$OUT"
# ソース .py のみを zip（__pycache__ / build / テストは除外）。
( cd "$SRC_DIR" && zip -r -X -q "$OUT" . \
    -x '*__pycache__*' \
    -x 'build/*' \
    -x '*.pyc' \
    -x 'requirements.txt' )

echo "== done. size: $(du -h "$OUT" | cut -f1)"
echo "== contents:"
unzip -l "$OUT"
