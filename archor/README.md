# Archor · 锚点前端

与 `anchor-backend/` 后端分离；推荐通过后端统一启动（API + 静态页）。

## 页面

| 页面 | 文件 | 说明 |
|------|------|------|
| P1 | `index.html` | 模式选择 + 输入框 |
| P2 | `p2.html` | Gemini 风格多轮对话 |
| P2 | `p2.html` | 对话收束 |
| P3 | `p3.html` | 锚点页（第一锚点多选 + 手绘图） |
| P4 | `p4.html` | 出行方式偏好（公交/地铁/骑行/步行/自驾） |
| P5 | `p5.html` | 跟随页推荐 |
| P6 | `p6.html` | 路书 Flipbook（推荐方案） |

## 高德地图

P3 日页右侧地图使用高德 JS API 2.0。密钥放在 `js/amap-config.js`（从 `js/amap-config.example.js` 复制），已在 `.gitignore` 中忽略。本地开发需在[高德控制台](https://console.amap.com/dev/key/app)为 Key 配置 `localhost` / `127.0.0.1` 白名单。

## 启动（推荐）

```bash
cd anchor-backend
./start.sh
```

或手动：

```bash
cd anchor-backend
.venv/bin/uvicorn api.server:app --host 127.0.0.1 --port 8000
```

打开 http://localhost:8000/archor/ （**不要**用 `file://` 打开 HTML）

若提示「无法连接后端」，说明 8000 端口服务未运行，在 `anchor-backend` 目录执行 `./start.sh` 即可。

## 仅静态预览（无对话 API）

```bash
python3 -m http.server 8765
```

打开 http://localhost:8765/archor/ — P2 会请求 `http://127.0.0.1:8000/api/chat`，需同时启动后端。

## 流程

P1 提交 → `sessionStorage` 写入 `archorPrompt` → 跳转 P2 → 自动发送首条消息 → 状态机采集四要素 → 收束后显示「生成推荐方案」→ P3
