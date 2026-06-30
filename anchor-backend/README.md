# 锚点 Anchor 后端

对话式 AI 旅游规划平台后端：多轮对话采集需求 → 量化推荐 → 生成可调整的 Flipbook 路书。

## 状态机

| 状态 | 说明 |
|------|------|
| `INIT` | 初始 |
| `SLOT_FILLING` | 资料收集（五要素） |
| `RISK_CLARIFY` | 体能风险拦截 |
| `CONVERGENCE` | 收束完成，进入方案生成 |

## 五要素槽位

对话需采集以下要素（`anchor/slots.py`）；P1 模式已隐含锚点大类时不重复追问 `anchor`：

- `destination` — 目的地（仅支持库内城市，见下）
- `days` — 天数（不确定时按模式给默认值）
- `anchor` — 出行锚点：吃 / 住 / 玩
- `tags` — 用户画像标签（同行人 / 身份，列表）
- `transport_preferences` — 出行方式偏好（地铁+步行 / 自驾等）

采集顺序：目的地 → 天数 → 出行方式 → 同行人画像。

## 支持城市与 POI 数据

数据库 `db/anchor.db` 已内置 4 座城市（每城约 16 景点 / 10 酒店 / 12 餐厅 + 交通段）：

- 北京、南京、重庆、新疆

> 用户输入库外城市（如上海/成都）会被友好拦截并引导改选。扩城方法：在 `db/` 种子脚本中补充对应 POI 与 `traffic_segment` 后重建库。

## 对话核心入口

```python
from anchor import Session, handle_user_message

session = Session()
turn = handle_user_message(session, "想去重庆玩3天，带长辈，路上地铁加步行", llm=your_llm_client, mode="ROUTE")
print(turn.reply)
session = turn.session
```

- `mode`：来自前端 P1 模式选择（`ROUTE` / `FOOD` / `FILL` / `EVENT`），用于隐含锚点大类与天数默认。
- 未传 `llm` 时使用规则 NLU + 模板追问（适合单测与本地调试）。

## LLM 接入

实现 `LLMClient` 协议（`complete(system, user) -> str`）即可；项目内置 `anchor/deepseek_client.py`，配置 `.env` 中的 `DEEPSEEK_API_KEY` 后自动启用，未配置则回退规则 NLU。

## 劳累度预计算

```
fatigue_index = Σ(tran_cost + attract_cost) + luggage_cost
tran_cost     = tran_time × tran_factor
attract_cost  = attract_time × attract_factor
用户体能上限   = resolve_fatigue_max(tags)   # 按最严格标签取值
hasConflict   = fatigue_index > 用户体能上限
```

公式实现见 `anchor/recommender.py`、`anchor/fatigue.py`；标签上限见 `anchor/tag_mapping.py`。

## 路书生成（Flipbook）

```
build_flipbook_plan(session)
  ├─ 选点：锚点 + 跟随 + 周边填充
  ├─ 动线：玩点最近邻聚类，远点自然成为独立一日游
  ├─ 交通：按用户出行偏好默认推荐各路段方式（分段速度估车程）
  └─ 诊断：attach_day_diagnoses() 逐日生成优点/缺陷（打分选最相关一条 + 跨天去重）
```

每日诊断缺陷规则（`anchor/day_advisor.py`）：`long_transfer` 跨城远征 / `backtrack` 折返 / `heavy_tran` 市内通勤偏多 / `heavy_attract` 暴走耗能 / `fatigue_over` 强度超标 / `low_matching_must` 匹配偏低。

## HTTP API（`api/server.py`，FastAPI）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET  | `/api/health` | 健康检查 + LLM 是否启用 |
| POST | `/api/chat` | 多轮对话 |
| POST | `/api/plan/shell` | 路书骨架（首屏占位） |
| POST | `/api/plan` | 生成完整 Flipbook 路书 |
| POST | `/api/wizard/follow` | 锚点后的跟随推荐 |
| GET  | `/api/transport/modes` | 出行方式目录 |

前端静态站点挂载在 `/archor/`（同仓库 `archor/` 目录，P1–P6 向导页）。

## 前端流程（`archor/`）

P1 模式选择 → P2 对话采集 → P3 选锚点 POI → P4 选跟随 POI → P5 确认出行方式 → P6 生成路书。

## 本地运行

```bash
cd anchor-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 db/init_db.py                      # 建表 + 种子数据（首次）
python3 -m unittest discover -s tests -q   # 跑测试
./start.sh                                 # 启动服务 → http://localhost:8000/archor/

## 部署到 Render（公网访问）

1. 把本仓库推到 GitHub（已完成：`nicolrjbit/Anchor`）。
2. 打开 [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**。
3. 连接 GitHub 仓库 **Anchor**，Render 会读取根目录 `render.yaml` 并创建 Web Service。
4. （可选）在 Service → **Environment** 添加 `DEEPSEEK_API_KEY`；不填则使用规则 NLU。
5. 部署完成后访问：`https://<你的服务名>.onrender.com/archor/`（根路径 `/` 会自动跳转）。

**手动创建 Web Service**（不用 Blueprint 时）：

| 项 | 值 |
|----|-----|
| Root Directory | `anchor-backend` |
| Build Command | `pip install -r requirements.txt && python db/init_db.py` |
| Start Command | `bash render_start.sh` |
| Health Check | `/api/health` |

**高德地图（P3/P6）**：在[高德控制台](https://console.amap.com/) Key 白名单加入 `*.onrender.com` 或你的具体域名；服务器上无法写入被 gitignore 的 `amap-config.js`，若需地图可改为在 Render 环境变量注入或提交 example 副本（勿泄露 Key）。

免费实例约 15 分钟无访问会休眠，首次打开需等待 ~30 秒冷启动。
```

## 数据库（`db/anchor.db`）

| 表 | 用途 |
|----|------|
| `map_attract_tier` | 景点等级 → attract_factor |
| `map_user_tag_matching` | 用户标签 × 景点等级 → matching_tag |
| `map_transport_mode` | 出行方式 → tran_factor |
| `map_user_fatigue_max` | 用户标签 → 单日劳累度上限 |
| `attractions` / `hotels` / `restaurants` | POI 基础数据（含 brief_intro） |
| `traffic_segment` | 节点间 tran_time / tran_factor / tran_mode |
| `user_profile` | 会话用户画像与标签 |
| `recomm_plan` / `recomm_info` | 方案级与明细级推荐字段 |
