-- 锚点 Anchor 平台数据库 Schema（仅表结构，无业务数据）
-- 公式说明见 anchor-backend/db/README.md

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 映射表（来源：映射表.md）
-- ---------------------------------------------------------------------------

-- 景点等级 → 景区系数 attract_factor（消耗分值）
CREATE TABLE IF NOT EXISTS map_attract_tier (
    tier            TEXT PRIMARY KEY,   -- 特级 | 高级 | 中级 | 低级
    attract_factor  REAL NOT NULL,    -- 5 | 3 | 2 | 1
    scene_desc      TEXT                -- 典型 POI 场景定义
);

-- 用户标签 × 景点等级 → matching_tag（用户标签匹配度）
CREATE TABLE IF NOT EXISTS map_user_tag_matching (
    user_tag        TEXT NOT NULL,      -- 大学生/年轻毕业生、带长辈出行 等
    attract_tier    TEXT NOT NULL,      -- 特级 | 高级 | 中级 | 低级
    matching_tag    REAL NOT NULL,
    PRIMARY KEY (user_tag, attract_tier),
    FOREIGN KEY (attract_tier) REFERENCES map_attract_tier(tier)
);

-- 出行方式 → tran_factor（交通方式系数）
CREATE TABLE IF NOT EXISTS map_transport_mode (
    tran_mode       TEXT PRIMARY KEY,   -- 汽车 | 地铁 | 骑行 | 步行
    tran_factor     REAL NOT NULL
);

-- 用户标签 → 单日劳累度上限 F_max
CREATE TABLE IF NOT EXISTS map_user_fatigue_max (
    user_tag        TEXT PRIMARY KEY,
    fatigue_max     REAL NOT NULL
);

-- ---------------------------------------------------------------------------
-- POI 基础表（吃住玩，数据待导入）
-- ---------------------------------------------------------------------------

-- 景点（玩）— 用户文档中写作 atrractions，此处规范为 attractions
CREATE TABLE IF NOT EXISTS attractions (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    address         TEXT,
    longitude       REAL,
    latitude        REAL,
    rating          REAL,               -- POI 评分，用于 matching_score / 填充过滤
    attract_tier    TEXT,               -- 特级 | 高级 | 中级 | 低级
    attract_time    REAL,               -- 景区游玩时长（小时）
    attract_factor  REAL,               -- 景区系数，可冗余存储或由 map_attract_tier 推导
    open_time       TEXT,
    tel             TEXT,
    ticket_price    TEXT,
    brief_intro     TEXT,               -- 景点简要介绍（展示用）
    visit_hours     REAL,               -- 兼容旧字段，可与 attract_time 同步
    raw_json        TEXT,
    FOREIGN KEY (attract_tier) REFERENCES map_attract_tier(tier)
);

CREATE TABLE IF NOT EXISTS hotels (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    address         TEXT,
    longitude       REAL,
    latitude        REAL,
    rating          REAL,
    star_level      TEXT,
    price_range     TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS restaurants (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    address         TEXT,
    longitude       REAL,
    latitude        REAL,
    rating          REAL,
    cuisine_type    TEXT,
    price_range     TEXT,
    raw_json        TEXT
);

-- ---------------------------------------------------------------------------
-- 用户画像（对话收集的四要素 + 标签，matching_tag 通过映射表关联查询）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_profile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    destination     TEXT,
    days            INTEGER,
    anchor          TEXT,               -- 锚点名称或 POI id
    anchor_poi_id   TEXT,               -- 锚点 POI 外键（待关联）
    tag             TEXT NOT NULL,      -- 单条用户标签，一行一标签
    fatigue_max     REAL,               -- 可由 map_user_fatigue_max 冗余写入
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (session_id, tag)
);

-- ---------------------------------------------------------------------------
-- 交通段：节点 A → 节点 B
-- tran_cost = tran_time * tran_factor（结果写入 recomm_info）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS traffic_segment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_poi_id     TEXT NOT NULL,
    from_poi_type   TEXT NOT NULL,      -- play | stay | eat
    to_poi_id       TEXT NOT NULL,
    to_poi_type     TEXT NOT NULL,
    tran_time       REAL NOT NULL,      -- 交通时间（分钟）
    tran_mode       TEXT NOT NULL,      -- 汽车 | 地铁 | 骑行 | 步行
    tran_factor     REAL,               -- 冗余，取自 map_transport_mode
    city            TEXT,
    FOREIGN KEY (tran_mode) REFERENCES map_transport_mode(tran_mode)
);

-- ---------------------------------------------------------------------------
-- 推荐方案与推荐明细
-- ---------------------------------------------------------------------------

-- 方案级：fatigue_index = Σ(tran_cost + attract_cost) + luggage_cost
CREATE TABLE IF NOT EXISTS recomm_plan (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    day_index       INTEGER NOT NULL,   -- 第几天，从 1 起
    mode            TEXT,               -- SCENIC | VACATION | FOOD | EVENT
    luggage_count   INTEGER DEFAULT 0,  -- 变更酒店次数
    fatigue_index   REAL,               -- 方案整体劳累度
    total_tran_cost       REAL,
    total_attract_cost    REAL,
    total_luggage_cost    REAL,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 推荐位明细：跟随 follow / 填充 fill
CREATE TABLE IF NOT EXISTS recomm_info (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id         INTEGER NOT NULL,
    reco_type       TEXT NOT NULL,      -- follow | fill
    anchor_poi_id   TEXT NOT NULL,      -- 所属锚点
    anchor_order    INTEGER NOT NULL,   -- 锚点顺序（按锚点依次推荐）
    poi_id          TEXT NOT NULL,
    poi_type        TEXT NOT NULL,      -- play | stay | eat
    rank            INTEGER NOT NULL,     -- 该锚点下 Top 1-3
    -- 评分与消耗（公式字段）
    rating          REAL,               -- 冗余，取自 POI 表
    matching_tag    REAL,               -- 用户标签匹配度，取自映射表
    matching_score  REAL,               -- rating * matching_tag
    tran_cost       REAL,               -- tran_time * tran_factor（跟随策略用）
    attract_cost    REAL,               -- attract_time * attract_factor
    luggage_cost    REAL,               -- 20 * luggage_count（方案级可只在 plan 汇总）
    follow_score    REAL,               -- matching_score - tran_cost（跟随排序依据）
    distance_km     REAL,               -- 与锚点距离（填充策略 1.5km 过滤）
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (plan_id) REFERENCES recomm_plan(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 索引
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_attractions_city ON attractions(city);
CREATE INDEX IF NOT EXISTS idx_attractions_rating ON attractions(rating);
CREATE INDEX IF NOT EXISTS idx_attractions_geo ON attractions(longitude, latitude);
CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city);
CREATE INDEX IF NOT EXISTS idx_restaurants_city ON restaurants(city);
CREATE INDEX IF NOT EXISTS idx_user_profile_session ON user_profile(session_id);
CREATE INDEX IF NOT EXISTS idx_recomm_plan_session ON recomm_plan(session_id);
CREATE INDEX IF NOT EXISTS idx_recomm_info_plan ON recomm_info(plan_id);
CREATE INDEX IF NOT EXISTS idx_recomm_info_anchor ON recomm_info(anchor_poi_id, reco_type);
CREATE INDEX IF NOT EXISTS idx_traffic_segment_pair ON traffic_segment(from_poi_id, to_poi_id);
