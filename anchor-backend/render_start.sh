#!/usr/bin/env bash
# Render Web Service 启动脚本（读取平台注入的 PORT）
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if [[ ! -f db/anchor.db ]]; then
  echo "初始化 POI 数据库…"
  python db/init_db.py
fi

echo "Anchor 启动 → 0.0.0.0:${PORT}  前端 /archor/"
exec uvicorn api.server:app --host 0.0.0.0 --port "${PORT}"
