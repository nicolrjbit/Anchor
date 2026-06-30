#!/usr/bin/env bash
# 启动 Anchor 后端（API + archor 静态页）
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "未找到 .venv，请先运行："
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f db/anchor.db ]]; then
  echo "初始化 POI 数据库…"
  .venv/bin/python db/init_db.py
fi

echo "Anchor 后端启动中 → http://localhost:8000/archor/"
exec .venv/bin/uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
