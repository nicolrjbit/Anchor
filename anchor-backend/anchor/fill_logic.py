"""填充逻辑：锚点周边 1.5km、评分≥4.6 的 Top3 POI。"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "anchor.db"
FILL_RADIUS_KM = 1.5
MIN_RATING = 4.6

FILL_STEPS = [
    {"id": "anchor", "label": "锁定第一锚点"},
    {"id": "follow", "label": "写入跟随推荐"},
    {"id": "fill", "label": "锚点周边 1.5km 高分填充"},
    {"id": "route", "label": "编排动线与交通"},
    {"id": "diag", "label": "AI 行程诊断"},
    {"id": "render", "label": "合成路书"},
]


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _load_poi_row(conn: sqlite3.Connection, poi_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, name, rating, longitude, latitude, '玩' AS poi_type FROM attractions WHERE id=?
        UNION ALL
        SELECT id, name, rating, longitude, latitude, '住' FROM hotels WHERE id=?
        UNION ALL
        SELECT id, name, rating, longitude, latitude, '吃' FROM restaurants WHERE id=?
        """,
        (poi_id, poi_id, poi_id),
    ).fetchone()


def build_fill_picks(
    session: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    limit: int = 3,
) -> list[dict[str, Any]]:
    slots = session.get("slots") or {}
    destination = slots.get("destination") or "重庆"
    exclude: set[str] = set()
    for key in ("selected_anchor_pois", "selected_follow_pois"):
        for item in session.get(key) or []:
            if isinstance(item, dict) and item.get("poi_id"):
                exclude.add(item["poi_id"])
    if session.get("selected_anchor_poi") and session["selected_anchor_poi"].get("poi_id"):
        exclude.add(session["selected_anchor_poi"]["poi_id"])

    anchors = list(session.get("selected_anchor_pois") or [])
    if not anchors and session.get("selected_anchor_poi"):
        anchors = [session.get("selected_anchor_poi")]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    results: list[dict[str, Any]] = []
    try:
        all_pois = conn.execute(
            """
            SELECT id, name, rating, longitude, latitude, '玩' AS poi_type FROM attractions WHERE city=?
            UNION ALL
            SELECT id, name, rating, longitude, latitude, '住' FROM hotels WHERE city=?
            UNION ALL
            SELECT id, name, rating, longitude, latitude, '吃' FROM restaurants WHERE city=?
            """,
            (destination, destination, destination),
        ).fetchall()

        for anchor in anchors:
            aid = anchor.get("poi_id")
            if not aid:
                continue
            arow = _load_poi_row(conn, aid)
            if not arow:
                continue
            alng, alat = float(arow["longitude"]), float(arow["latitude"])
            nearby: list[tuple[float, sqlite3.Row]] = []
            for p in all_pois:
                if p["id"] in exclude or p["id"] == aid:
                    continue
                rating = float(p["rating"] or 0)
                if rating < MIN_RATING:
                    continue
                dist = _haversine_km(alng, alat, float(p["longitude"]), float(p["latitude"]))
                if dist <= FILL_RADIUS_KM:
                    nearby.append((dist, p))
            nearby.sort(key=lambda x: (-float(x[1]["rating"] or 0), x[0]))
            picks = []
            for i, (dist, p) in enumerate(nearby[:limit], start=1):
                picks.append(
                    {
                        "rank": i,
                        "poi_id": p["id"],
                        "name": p["name"],
                        "poi_type": p["poi_type"],
                        "rating": float(p["rating"] or 0),
                        "distance_km": round(dist, 2),
                        "anchor_poi_id": aid,
                        "anchor_name": arow["name"],
                    }
                )
            results.append({"anchor_poi_id": aid, "anchor_name": arow["name"], "picks": picks})
    finally:
        conn.close()
    return results
