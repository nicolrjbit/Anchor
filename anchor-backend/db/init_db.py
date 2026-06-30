"""初始化锚点数据库（表结构 + 映射表 + 四城 POI 种子数据）。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "anchor.db"

_DB_DIR = Path(__file__).resolve().parent
if str(_DB_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_DB_DIR.parent))

from db.seed_poi_data import seed_poi_tables  # noqa: E402

# 映射表.md 中的种子数据
MAP_ATTRACT_TIER = [
    ("特级", 5.0, "爬山/户外徒步、大型主题乐园、大型风景区暴走"),
    ("高级", 3.0, "大型室内展馆、大型商圈扫街、历史古镇、大型野生动物园"),
    ("中级", 2.0, "城市综合公园、小型美术馆、网红打卡街区、寺庙祈福"),
    ("低级", 1.0, "网红咖啡/茶馆、独立书店、游船坐票、江景露台、SPA/足疗"),
]

MAP_USER_TAG_MATCHING = [
    ("大学生/年轻毕业生", "特级", 1.2),
    ("大学生/年轻毕业生", "高级", 1.0),
    ("大学生/年轻毕业生", "中级", 1.0),
    ("大学生/年轻毕业生", "低级", 0.8),
    ("长途长假游客", "特级", 1.1),
    ("长途长假游客", "高级", 1.2),
    ("长途长假游客", "中级", 0.8),
    ("长途长假游客", "低级", 0.5),
    ("上班族", "特级", 0.3),
    ("上班族", "高级", 0.8),
    ("上班族", "中级", 1.0),
    ("上班族", "低级", 1.2),
    ("亲子游家庭", "特级", 0.2),
    ("亲子游家庭", "高级", 0.9),
    ("亲子游家庭", "中级", 1.2),
    ("亲子游家庭", "低级", 0.7),
    ("带长辈出行", "特级", 0.1),
    ("带长辈出行", "高级", 0.7),
    ("带长辈出行", "中级", 1.1),
    ("带长辈出行", "低级", 1.2),
    ("年轻情侣/朋友", "特级", 1.0),
    ("年轻情侣/朋友", "高级", 1.0),
    ("年轻情侣/朋友", "中级", 1.2),
    ("年轻情侣/朋友", "低级", 1.1),
    ("单身独居青年", "特级", 0.6),
    ("单身独居青年", "高级", 1.0),
    ("单身独居青年", "中级", 1.0),
    ("单身独居青年", "低级", 1.2),
    ("追星族/赛事爱好者", "特级", 0.5),
    ("追星族/赛事爱好者", "高级", 0.8),
    ("追星族/赛事爱好者", "中级", 1.0),
    ("追星族/赛事爱好者", "低级", 1.0),
    ("商务出差", "特级", 0.1),
    ("商务出差", "高级", 0.5),
    ("商务出差", "中级", 0.8),
    ("商务出差", "低级", 1.2),
]

MAP_TRANSPORT_MODE = [
    ("汽车", 1.0),
    ("地铁", 1.2),
    ("骑行", 1.6),
    ("步行", 2.0),
]

MAP_USER_FATIGUE_MAX = [
    ("大学生/年轻毕业生", 180),
    ("追星族/赛事爱好者", 160),
    ("年轻情侣/朋友", 140),
    ("长途长假游客", 120),
    ("单身独居青年", 110),
    ("上班族", 100),
    ("商务出差", 90),
    ("亲子游家庭", 80),
    ("带长辈出行", 50),
]

# 对话标签 → 映射表 user_tag 别名（后续 NLU 标签规范化用）
TAG_ALIAS = {
    "特种兵": "大学生/年轻毕业生",
    "景点打卡": "长途长假游客",
    "行程节奏紧凑": "大学生/年轻毕业生",
    "酒店度假": "上班族",
    "行程节奏宽松": "上班族",
    "控制劳累度": "带长辈出行",
    "亲子游": "亲子游家庭",
    "带长辈": "带长辈出行",
    "长辈出行": "带长辈出行",
    "美食寻味": "年轻情侣/朋友",
    "周末出行": "年轻情侣/朋友",
    "短途": "单身独居青年",
    "固定时间": "追星族/赛事爱好者",
    "轻度打卡": "商务出差",
}


def init_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    seed_maps: bool = True,
    seed_poi: bool = True,
) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_schema_migrations(conn)
        if seed_maps:
            _seed_mapping_tables(conn)
        if seed_poi:
            poi_counts = seed_poi_tables(conn)
            print(f"POI 种子数据: {poi_counts}")
        conn.commit()
    finally:
        conn.close()

    return db_path


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(attractions)")}
    if "brief_intro" not in cols:
        conn.execute("ALTER TABLE attractions ADD COLUMN brief_intro TEXT")


def _seed_mapping_tables(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO map_attract_tier (tier, attract_factor, scene_desc) VALUES (?, ?, ?)",
        MAP_ATTRACT_TIER,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO map_user_tag_matching (user_tag, attract_tier, matching_tag) VALUES (?, ?, ?)",
        MAP_USER_TAG_MATCHING,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO map_transport_mode (tran_mode, tran_factor) VALUES (?, ?)",
        MAP_TRANSPORT_MODE,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO map_user_fatigue_max (user_tag, fatigue_max) VALUES (?, ?)",
        MAP_USER_FATIGUE_MAX,
    )


if __name__ == "__main__":
    path = init_db()
    print(f"数据库已初始化: {path}")
