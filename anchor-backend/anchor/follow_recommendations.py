"""跟随页：按锚点推荐 follow 类型 POI（matching_score - tran_cost Top3）。"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anchor.poi_sketches import sketch_url
from anchor.recommender import calc_matching_score, calc_tran_cost
from anchor.tag_mapping import db_user_tag, resolve_profile_tags
from anchor.travel_modes import resolve_travel_mode

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "anchor.db"

TYPE_LABEL = {"玩": "景点", "住": "酒店", "吃": "餐厅"}


@dataclass
class FollowPick:
    rank: int
    poi_id: str
    name: str
    poi_type: str
    rating: float
    matching_score: float
    tran_cost: float
    composite_score: float
    distance_km: float
    reason: str
    sketch_image: str
    anchor_poi_id: str
    anchor_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "poi_id": self.poi_id,
            "name": self.name,
            "poi_type": self.poi_type,
            "rating": self.rating,
            "matching_score": self.matching_score,
            "tran_cost": self.tran_cost,
            "composite_score": self.composite_score,
            "distance_km": self.distance_km,
            "reason": self.reason,
            "sketch_image": self.sketch_image,
            "anchor_poi_id": self.anchor_poi_id,
            "anchor_name": self.anchor_name,
        }


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _follow_reason(
    *,
    follow_type: str,
    name: str,
    anchor_name: str,
    distance_km: float,
    rating: float,
    brief_intro: str | None = None,
) -> str:
    if follow_type == "玩" and brief_intro:
        return brief_intro
    return _friendly_reason(
        follow_type=follow_type,
        name=name,
        anchor_name=anchor_name,
        distance_km=distance_km,
        rating=rating,
    )


def _friendly_reason(
    *,
    follow_type: str,
    name: str,
    anchor_name: str,
    distance_km: float,
    rating: float,
) -> str:
    label = TYPE_LABEL.get(follow_type, follow_type)
    if distance_km < 0.8:
        dist = "离锚点很近，走几步就到"
    elif distance_km < 2:
        dist = f"离「{anchor_name}」大概 {distance_km:.1f} 公里，动线顺"
    else:
        dist = f"稍远一点（约 {distance_km:.1f} 公里），但综合分还是靠前"
    return f"给你挑的这家{label}「{name}」，{dist}，评分 {rating:.1f}，跟着锚点走不太绕路。"


def build_follow_recommendations(
    session: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    limit: int = 3,
) -> dict[str, Any]:
    spec = resolve_travel_mode(session)
    follow_type = spec.follow_type
    slots = session.get("slots") or {}
    destination = slots.get("destination") or "重庆"
    tags = resolve_profile_tags(list(slots.get("tags") or []))
    user_tag = db_user_tag(tags[0]) if tags else "上班族"

    anchors = list(session.get("selected_anchor_pois") or [])
    if not anchors and session.get("selected_anchor_poi"):
        anchors = [session.get("selected_anchor_poi")]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        anchor_coords: dict[str, tuple[float, float, str]] = {}
        for a in anchors:
            aid = a.get("poi_id")
            if not aid:
                continue
            row = conn.execute(
                """
                SELECT id, name, longitude, latitude FROM attractions WHERE id=?
                UNION ALL SELECT id, name, longitude, latitude FROM hotels WHERE id=?
                UNION ALL SELECT id, name, longitude, latitude FROM restaurants WHERE id=?
                """,
                (aid, aid, aid),
            ).fetchone()
            if row:
                anchor_coords[aid] = (float(row["longitude"]), float(row["latitude"]), row["name"])

        if follow_type == "玩":
            candidates_sql = """
                SELECT id, name, rating, longitude, latitude, attract_tier AS tier,
                       NULL AS cuisine, brief_intro
                FROM attractions WHERE city = ?
            """
        elif follow_type == "住":
            candidates_sql = """
                SELECT id, name, rating, longitude, latitude, NULL AS tier,
                       NULL AS cuisine, NULL AS brief_intro
                FROM hotels WHERE city = ?
            """
        else:
            candidates_sql = """
                SELECT id, name, rating, longitude, latitude, NULL AS tier,
                       cuisine_type AS cuisine, NULL AS brief_intro
                FROM restaurants WHERE city = ?
            """

        candidates = conn.execute(candidates_sql, (destination,)).fetchall()
        matching_map = {
            str(r["attract_tier"]): float(r["matching_tag"])
            for r in conn.execute(
                "SELECT attract_tier, matching_tag FROM map_user_tag_matching WHERE user_tag = ?",
                (user_tag,),
            )
        }

        selected_ids = {a.get("poi_id") for a in anchors if a.get("poi_id")}
        groups: list[dict[str, Any]] = []

        for anchor in anchors:
            aid = anchor.get("poi_id")
            if not aid or aid not in anchor_coords:
                continue
            alng, alat, aname = anchor_coords[aid]
            scored: list[FollowPick] = []
            for c in candidates:
                cid = c["id"]
                if cid in selected_ids:
                    continue
                dist = _haversine_km(alng, alat, float(c["longitude"]), float(c["latitude"]))
                tran_min = max(5.0, dist * 5.0)
                tran_cost = calc_tran_cost(tran_min, 1.2)
                tier = c["tier"] or "中级"
                tag_coef = matching_map.get(tier, 1.0) if follow_type == "玩" else 1.0
                ms = calc_matching_score(float(c["rating"] or 0), tag_coef)
                composite = ms - tran_cost
                scored.append(
                    FollowPick(
                        rank=0,
                        poi_id=cid,
                        name=c["name"],
                        poi_type=follow_type,
                        rating=float(c["rating"] or 0),
                        matching_score=round(ms, 1),
                        tran_cost=round(tran_cost, 1),
                        composite_score=round(composite, 1),
                        distance_km=round(dist, 1),
                        reason=_follow_reason(
                            follow_type=follow_type,
                            name=c["name"],
                            anchor_name=aname,
                            distance_km=dist,
                            rating=float(c["rating"] or 0),
                            brief_intro=str(c["brief_intro"] or "") or None,
                        ),
                        sketch_image=sketch_url(cid),
                        anchor_poi_id=aid,
                        anchor_name=aname,
                    )
                )
            scored.sort(key=lambda x: x.composite_score, reverse=True)
            picks = []
            for i, p in enumerate(scored[:limit], start=1):
                item = FollowPick(**{**p.__dict__, "rank": i})
                picks.append(item.to_dict())
            groups.append(
                {
                    "anchor_poi_id": aid,
                    "anchor_name": aname,
                    "follow_type": follow_type,
                    "follow_label": TYPE_LABEL.get(follow_type, follow_type),
                    "picks": picks,
                }
            )
    finally:
        conn.close()

    return {
        "travel_mode": spec.code,
        "travel_mode_name": spec.name,
        "follow_type": follow_type,
        "follow_label": TYPE_LABEL.get(follow_type, follow_type),
        "groups": groups,
    }
