# Anchor

对话式 AI 旅游规划平台：P1–P6 向导流程 + Python 后端（槽位/NLU/路书生成）。

## 结构

| 目录 | 说明 |
|------|------|
| `anchor-backend/` | FastAPI 后端、POI 数据库、排日与诊断 |
| `archor/` | 前端静态页（P1–P6） |

## 本地运行

```bash
# 后端
cd anchor-backend
python3 -m db.init_db
python3 -m uvicorn anchor.main:app --reload

# 前端：用任意静态服务器打开 archor/index.html
```

详见 `anchor-backend/README.md`。
