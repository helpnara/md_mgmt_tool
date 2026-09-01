#!/usr/bin/env bash
# 로컬 실행 스크립트. 프론트엔드를 빌드한 뒤 FastAPI 하나로 서비스한다.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PYTHON="${PYTHON:-.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
  echo "가상환경이 없습니다. 먼저 아래를 실행하세요:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

# 프론트엔드 빌드 결과가 없으면 한 번 빌드한다 (node 필요).
if [ ! -d frontend/dist ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "프론트엔드를 빌드합니다…"
    (cd frontend && npm install --silent && npm run build)
  else
    echo "node/npm이 없어 프론트엔드를 빌드하지 못했습니다. API만 실행합니다."
  fi
fi

echo "http://127.0.0.1:${PORT} 에서 실행합니다. (Ctrl+C로 종료)"
exec "$PYTHON" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$PORT"
