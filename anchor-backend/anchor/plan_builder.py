"""从 Session 槽位 + POI 库生成 Flipbook 路书 JSON。"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anchor.day_advisor import attach_day_diagnoses
from anchor.plan_diagnosis import PlanDayMetrics, PlanMetrics, MustVisitPoi
from anchor.recommender import (
    LUGGAGE_UNIT_COST,
    calc_attract_cost,
    calc_fatigue_index,
    calc_matching_score,
    calc_tran_cost,
)
from anchor.tag_mapping import db_user_tag, resolve_profile_tags
from anchor.transport_planner import (
    apply_transport_modes,
    extract_transport_legs,
    merge_transport_selections,
    refresh_leg_costs,
)
from anchor.transport_mapping import describe_transport_preferences, resolve_session_transport_preferences
from anchor.travel_modes import resolve_plan_days, resolve_travel_mode, slot_order_for_session
from anchor.fill_logic import FILL_STEPS, build_fill_picks

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "anchor.db"

# 本地渐变占位，封面图异步加载，不阻塞首屏
CITY_HERO: dict[str, str] = {
    "北京": "https://images.unsplash.com/photo-1508804185872-d7badad00f7d?w=1200&q=70",
    "南京": "https://images.unsplash.com/photo-1599571234901-fb5940cab586?w=1200&q=70",
    "重庆": "https://images.unsplash.com/photo-1596436889106-be35e8431314?w=1200&q=70",
    "新疆": "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=1200&q=70",
    "成都": "https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=1200&q=70",
    "西安": "https://images.unsplash.com/photo-1547981609-4b4b4b4b4b4b?w=1200&q=70",
}

CITY_GRADIENT: dict[str, str] = {
    "北京": "linear-gradient(135deg, #c4a882 0%, #8b7355 100%)",
    "南京": "linear-gradient(135deg, #9eb4c8 0%, #5a7a96 100%)",
    "重庆": "linear-gradient(135deg, #8fa8b8 0%, #4a6678 100%)",
    "新疆": "linear-gradient(135deg, #d4b896 0%, #a08060 100%)",
    "成都": "linear-gradient(135deg, #a8c4a0 0%, #5a7a52 100%)",
    "西安": "linear-gradient(135deg, #c9a882 0%, #8b6914 100%)",
}

PACE_TITLE: dict[str, str] = {
    "normal": "顺路",
    "relaxed": "松弛感轻调",
    "compact": "紧凑高能",
}

ANCHOR_ORDER: dict[str, list[str]] = {
    "玩": ["玩", "吃", "玩", "吃", "住"],
    "吃": ["吃", "玩", "吃", "玩", "住"],
    "住": ["住", "玩", "吃", "玩", "吃"],
}

DAY_SLOTS = [
    ("09:30", 0),
    ("12:00", 1),
    ("15:00", 2),
    ("18:30", 3),
    ("21:00", 4),
]

_PLAN_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 600
# 路书 JSON 结构/文案逻辑变更时递增，使前后端与浏览器缓存失效
PLAN_CONTENT_VERSION = "wizard-v5"


@dataclass
class PoiPoint:
    id: str
    name: str
    poi_type: str
    rating: float
    lng: float
    lat: float
    attract_time: float = 2.0
    attract_factor: float = 2.0
    tier: str = "中级"
    open_time: str = ""
    ticket_price: str = ""
    cuisine_type: str = ""


def session_plan_key(session: dict[str, Any]) -> str:
    slots = session.get("slots") or {}
    tags = resolve_profile_tags(list(slots.get("tags") or []))
    selected_ids = _selected_poi_ids(session)
    follow_ids = _selected_follow_ids(session)
    transport_modes = session.get("transport_modes") or {}
    mode_sig = ",".join(f"{k}:{v}" for k, v in sorted(transport_modes.items()))
    pref_sig = ",".join(resolve_session_transport_preferences(session))
    travel = resolve_travel_mode(session).code
    return "|".join(
        [
            PLAN_CONTENT_VERSION,
            travel,
            str(slots.get("destination") or ""),
            str(slots.get("days") or ""),
            str(slots.get("anchor") or ""),
            ",".join(tags),
            str(session.get("pace_modifier") or "normal"),
            str((session.get("conflict_detail") or {}).get("fatigue_score") or ""),
            ",".join(selected_ids),
            ",".join(follow_ids),
            pref_sig,
            mode_sig,
        ]
    )


def _selected_follow_ids(session: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in session.get("selected_follow_pois") or []:
        if isinstance(item, dict):
            pid = str(item.get("poi_id") or "")
            if pid and pid not in ids:
                ids.append(pid)
    return ids


def _selected_poi_ids(session: dict[str, Any]) -> list[str]:
    raw = session.get("selected_anchor_pois") or []
    if not raw and session.get("selected_anchor_poi"):
        raw = [session.get("selected_anchor_poi")]
    ids: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("poi_id") or item.get("name") or "")
        if pid and pid not in ids:
            ids.append(pid)
    return ids


def _connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"数据库不存在: {path}，请先运行 python db/init_db.py")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _companion_capsule(tags: list[str]) -> str:
    joined = " ".join(tags)
    if any(k in joined for k in ("情侣", "朋友")):
        return "双人出行"
    if any(k in joined for k in ("亲子", "带娃")):
        return "家庭出行"
    if any(k in joined for k in ("长辈", "爸妈")):
        return "陪长辈出行"
    if "独自" in joined or "单身" in joined:
        return "独自出行"
    return "结伴出行"


def _cover_meta(session: dict[str, Any]) -> dict[str, Any]:
    slots = session.get("slots") or {}
    destination = slots.get("destination") or "重庆"
    days = resolve_plan_days(session)
    anchor = slots.get("anchor") or "玩"
    tags = resolve_profile_tags(list(slots.get("tags") or []))
    pace = session.get("pace_modifier") or "normal"
    fatigue_score = int((session.get("conflict_detail") or {}).get("fatigue_score") or 28)
    profile = tags[0] if tags else "旅行者"
    title = f"{destination}{days}日游"
    cover_tags = [t for t in (tags[:2] + [_companion_capsule(tags)]) if t][:3]
    return {
        "title": title,
        "hero_image": CITY_HERO.get(destination, CITY_HERO["重庆"]),
        "hero_gradient": CITY_GRADIENT.get(destination, CITY_GRADIENT["重庆"]),
        "destination": destination,
        "days": days,
        "tags": cover_tags,
        "total_fatigue_score": fatigue_score,
        "total_commute_km": None,
        "anchor": anchor,
    }


def build_plan_shell(session: dict[str, Any]) -> dict[str, Any]:
    """无 DB 访问，毫秒级返回路书框架（封面 + 空白日页 + 封底）。"""
    cover = _cover_meta(session)
    days_count = cover["days"]
    skeleton_days = [
        {
            "day_index": i,
            "timeline": [],
            "route": [],
            "pros": [],
            "cons": [],
            "ready": False,
        }
        for i in range(1, days_count + 1)
    ]
    return {
        "shell": True,
        "cover": cover,
        "days": skeleton_days,
        "back": {
            "pdf_label": "下载 PDF 路书",
            "share_label": "生成长图分享",
            "share_url": f"/archor/p6.html?city={cover['destination']}",
        },
        "eta_seconds": max(2, min(6, 1 + days_count)),
    }


def _load_city_bundle(
    conn: sqlite3.Connection, city: str, user_tag: str
) -> tuple[dict[str, list[PoiPoint]], dict[tuple[str, str], tuple[float, float, str]], dict[str, float]]:
    plays = [
        PoiPoint(
            id=r["id"],
            name=r["name"],
            poi_type="玩",
            rating=float(r["rating"] or 0),
            lng=float(r["longitude"]),
            lat=float(r["latitude"]),
            attract_time=float(r["attract_time"] or 2),
            attract_factor=float(r["attract_factor"] or 2),
            tier=r["attract_tier"] or "中级",
            open_time=str(r["open_time"] or ""),
            ticket_price=str(r["ticket_price"] or ""),
        )
        for r in conn.execute(
            """
            SELECT id, name, rating, longitude, latitude, attract_time, attract_factor, attract_tier,
                   open_time, ticket_price
            FROM attractions WHERE city = ? ORDER BY rating DESC
            """,
            (city,),
        )
    ]
    stays = [
        PoiPoint(
            id=r["id"],
            name=r["name"],
            poi_type="住",
            rating=float(r["rating"] or 0),
            lng=float(r["longitude"]),
            lat=float(r["latitude"]),
        )
        for r in conn.execute(
            "SELECT id, name, rating, longitude, latitude FROM hotels WHERE city = ? ORDER BY rating DESC",
            (city,),
        )
    ]
    eats = [
        PoiPoint(
            id=r["id"],
            name=r["name"],
            poi_type="吃",
            rating=float(r["rating"] or 0),
            lng=float(r["longitude"]),
            lat=float(r["latitude"]),
            cuisine_type=str(r["cuisine_type"] or ""),
        )
        for r in conn.execute(
            "SELECT id, name, rating, longitude, latitude, cuisine_type FROM restaurants WHERE city = ? ORDER BY rating DESC",
            (city,),
        )
    ]

    traffic: dict[tuple[str, str], tuple[float, float, str]] = {}
    for r in conn.execute(
        "SELECT from_poi_id, to_poi_id, tran_time, tran_factor, tran_mode FROM traffic_segment WHERE city = ?",
        (city,),
    ):
        traffic[(r["from_poi_id"], r["to_poi_id"])] = (
            float(r["tran_time"]),
            float(r["tran_factor"]),
            str(r["tran_mode"]),
        )

    matching: dict[str, float] = {}
    for r in conn.execute(
        "SELECT attract_tier, matching_tag FROM map_user_tag_matching WHERE user_tag = ?",
        (user_tag,),
    ):
        matching[str(r["attract_tier"])] = float(r["matching_tag"])

    return {"玩": plays, "住": stays, "吃": eats}, traffic, matching


def _pick_poi(pool: list[PoiPoint], day_index: int, slot: int) -> PoiPoint | None:
    if not pool:
        return None
    return pool[(day_index * 3 + slot) % len(pool)]


def _find_poi_in_pool(pool: list[PoiPoint], selected: dict[str, Any] | None) -> PoiPoint | None:
    if not selected or not pool:
        return None
    sel_id = selected.get("poi_id")
    if sel_id:
        for poi in pool:
            if poi.id == sel_id:
                return poi
    sel_name = selected.get("name")
    if sel_name:
        for poi in pool:
            if poi.name == sel_name:
                return poi
    return None


def _parse_selected_anchor_pois(
    session: dict[str, Any],
    pois: dict[str, list[PoiPoint]],
) -> tuple[list[PoiPoint], PoiPoint | None, PoiPoint | None]:
    """解析用户锚点选择 → (玩多选列表, 住, 吃)。"""
    raw = list(session.get("selected_anchor_pois") or [])
    if not raw and session.get("selected_anchor_poi"):
        raw = [session.get("selected_anchor_poi")]

    play_picks: list[PoiPoint] = []
    hotel: PoiPoint | None = None
    eat: PoiPoint | None = None
    seen_play: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        poi_type = item.get("poi_type")
        pool = pois.get(str(poi_type) or "", [])
        matched = _find_poi_in_pool(pool, item)
        if not matched:
            continue
        if matched.poi_type == "玩" and matched.id not in seen_play:
            play_picks.append(matched)
            seen_play.add(matched.id)
        elif matched.poi_type == "住":
            hotel = matched
        elif matched.poi_type == "吃":
            eat = matched
    return play_picks, hotel, eat


def _slot_keys_for_category(days: int, order: list[str], category: str) -> list[tuple[int, int]]:
    keys: list[tuple[int, int]] = []
    for day_i in range(1, days + 1):
        for _time_label, slot_idx in DAY_SLOTS:
            if slot_idx >= len(order):
                continue
            if order[slot_idx] == category:
                keys.append((day_i, slot_idx))
    return keys


def _play_slot_keys(days: int, order: list[str]) -> list[tuple[int, int]]:
    return _slot_keys_for_category(days, order, "玩")


def _expand_unique_candidates(
    selected: list[PoiPoint],
    pool: list[PoiPoint],
    need: int,
) -> list[PoiPoint]:
    """必选 POI 优先，再按评分补足，全程尽量不重复。"""
    seen: set[str] = set()
    out: list[PoiPoint] = []
    for poi in selected:
        if poi.id not in seen:
            out.append(poi)
            seen.add(poi.id)
    for poi in sorted(pool, key=lambda p: (-p.rating, p.name)):
        if len(out) >= need:
            break
        if poi.id not in seen:
            out.append(poi)
            seen.add(poi.id)
    return out


def _assign_slots_by_day(
    slot_keys: list[tuple[int, int]],
    candidates: list[PoiPoint],
    pool: list[PoiPoint],
) -> dict[tuple[int, int], PoiPoint]:
    """按日分配：同一天不重复，全程优先不重复。"""
    if not slot_keys:
        return {}

    by_day: dict[int, list[tuple[int, int]]] = {}
    for key in slot_keys:
        by_day.setdefault(key[0], []).append(key)

    ranked_pool = sorted(pool, key=lambda p: (-p.rating, p.name))
    result: dict[tuple[int, int], PoiPoint] = {}
    trip_used: set[str] = set()
    cand_idx = 0

    for day_i in sorted(by_day.keys()):
        day_used: set[str] = set()
        for key in by_day[day_i]:
            poi: PoiPoint | None = None
            while cand_idx < len(candidates):
                candidate = candidates[cand_idx]
                cand_idx += 1
                if candidate.id not in day_used:
                    poi = candidate
                    break
            if poi is None:
                for candidate in ranked_pool:
                    if candidate.id not in day_used and candidate.id not in trip_used:
                        poi = candidate
                        break
            if poi is None:
                for candidate in ranked_pool:
                    if candidate.id not in day_used:
                        poi = candidate
                        break
            if poi:
                result[key] = poi
                day_used.add(poi.id)
                trip_used.add(poi.id)
    return result


def _fallback_tran_minutes(leg_km: float) -> float:
    """无交通段数据时按分段速度估车程，避免长途被线性放大失真。

    市区段约 20km/h（含换乘/红绿灯），跨城段约 70km/h（高速），叠加固定上车开销。
    例：2km≈12min；12km≈42min；100km≈约 2 小时，而非旧公式的 7.5 小时。
    """
    if leg_km <= 0:
        return 0.0
    city_km = min(leg_km, 12.0)
    intercity_km = max(0.0, leg_km - 12.0)
    return 6.0 + city_km * 3.0 + intercity_km * 0.9


def _leg_tran(
    from_poi: PoiPoint,
    to_poi: PoiPoint,
    traffic: dict[tuple[str, str], tuple[float, float, str]],
) -> tuple[float, float, str]:
    """返回 (tran_min, tran_factor, tran_mode)，缺段时用分段速度兜底。"""
    leg_km = _haversine_km(from_poi.lng, from_poi.lat, to_poi.lng, to_poi.lat)
    seg = traffic.get((from_poi.id, to_poi.id))
    if seg:
        return seg
    tran_min = _fallback_tran_minutes(leg_km)
    mode = "自驾" if leg_km > 25 else "地铁"
    return tran_min, 1.2, mode


def _estimate_leg_tran_cost(
    from_poi: PoiPoint,
    to_poi: PoiPoint,
    traffic: dict[tuple[str, str], tuple[float, float, str]],
) -> float:
    tran_min, tran_factor, _ = _leg_tran(from_poi, to_poi, traffic)
    return calc_tran_cost(tran_min, tran_factor)


def _estimate_day_route_tran(
    day_i: int,
    order: list[str],
    play_schedule: dict[tuple[int, int], PoiPoint],
    eat_schedule: dict[tuple[int, int], PoiPoint],
    hotel: PoiPoint,
    traffic: dict[tuple[str, str], tuple[float, float, str]],
) -> float:
    """估算某日按 slot 顺序走完全程的交通消耗（用于选最近力酒店）。"""
    prev: PoiPoint | None = None
    total = 0.0
    for _time_label, slot_idx in DAY_SLOTS:
        if slot_idx >= len(order):
            continue
        cat = order[slot_idx]
        key = (day_i, slot_idx)
        if cat == "住":
            poi = hotel
        elif cat == "玩":
            poi = play_schedule.get(key)
        elif cat == "吃":
            poi = eat_schedule.get(key)
        else:
            poi = None
        if not poi:
            continue
        if prev:
            total += _estimate_leg_tran_cost(prev, poi, traffic)
        prev = poi
    return total


def _hotel_candidates(selected: list[PoiPoint], pool: list[PoiPoint]) -> list[PoiPoint]:
    seen: set[str] = set()
    out: list[PoiPoint] = []
    for poi in selected + sorted(pool, key=lambda p: (-p.rating, p.name)):
        if poi.id not in seen:
            out.append(poi)
            seen.add(poi.id)
    return out


def _build_fatigue_optimized_hotel_schedule(
    days: int,
    order: list[str],
    selected: list[PoiPoint],
    pool: list[PoiPoint],
    play_schedule: dict[tuple[int, int], PoiPoint],
    eat_schedule: dict[tuple[int, int], PoiPoint],
    traffic: dict[tuple[str, str], tuple[float, float, str]],
) -> dict[tuple[int, int], PoiPoint]:
    """按日选酒店：优先贴近当日景点动线，换房计入行李搬运消耗。"""
    keys = _slot_keys_for_category(days, order, "住")
    if not keys or not pool:
        return {}

    candidates = _hotel_candidates(selected, pool)
    by_day: dict[int, list[tuple[int, int]]] = {}
    for key in keys:
        by_day.setdefault(key[0], []).append(key)

    prev_hotel: PoiPoint | None = None
    day_hotels: dict[int, PoiPoint] = {}
    for day_i in sorted(by_day.keys()):
        best_hotel: PoiPoint | None = None
        best_cost = float("inf")
        for hotel in candidates:
            route_cost = _estimate_day_route_tran(
                day_i, order, play_schedule, eat_schedule, hotel, traffic
            )
            switch_cost = (
                LUGGAGE_UNIT_COST if prev_hotel and prev_hotel.id != hotel.id else 0.0
            )
            total = route_cost + switch_cost
            if total < best_cost:
                best_cost = total
                best_hotel = hotel
        if best_hotel:
            day_hotels[day_i] = best_hotel
            prev_hotel = best_hotel

    return {key: day_hotels[key[0]] for key in keys if key[0] in day_hotels}


def _count_hotel_switches(stay_schedule: dict[tuple[int, int], PoiPoint]) -> int:
    """连续两天酒店不同则计一次换房。"""
    by_day: dict[int, PoiPoint] = {}
    for (day_i, _slot), hotel in stay_schedule.items():
        by_day[day_i] = hotel
    switches = 0
    prev_id: str | None = None
    for day_i in sorted(by_day.keys()):
        hid = by_day[day_i].id
        if prev_id is not None and hid != prev_id:
            switches += 1
        prev_id = hid
    return switches


def _dedupe_consecutive_play(schedule: list[PoiPoint], pool: list[PoiPoint]) -> list[PoiPoint]:
    if len(schedule) <= 1 or not pool:
        return schedule
    result = list(schedule)
    for i in range(1, len(result)):
        if result[i].id != result[i - 1].id:
            continue
        alt = next((p for p in pool if p.id != result[i].id), None)
        if alt:
            result[i] = alt
    return result


def _nearest_neighbor_chain(points: list[PoiPoint]) -> list[PoiPoint]:
    if len(points) <= 2:
        return list(points)
    cx = sum(p.lng for p in points) / len(points)
    cy = sum(p.lat for p in points) / len(points)
    remaining = list(points)
    start = min(remaining, key=lambda p: _haversine_km(p.lng, p.lat, cx, cy))
    chain = [start]
    remaining.remove(start)
    while remaining:
        last = chain[-1]
        nxt = min(
            remaining,
            key=lambda p: _haversine_km(last.lng, last.lat, p.lng, p.lat),
        )
        chain.append(nxt)
        remaining.remove(nxt)
    return chain


GEO_CLUSTER_KM = 40.0


def _cluster_pois_by_distance(
    points: list[PoiPoint],
    threshold_km: float = GEO_CLUSTER_KM,
) -> list[list[PoiPoint]]:
    """单链聚类：相距 <= threshold 的玩点合并为同一「片区 / 基地」。"""
    if not points:
        return []
    if len(points) == 1:
        return [list(points)]
    clusters: list[list[PoiPoint]] = [[p] for p in points]
    while len(clusters) > 1:
        best_i, best_j, best_d = -1, -1, float("inf")
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = min(
                    _haversine_km(a.lng, a.lat, b.lng, b.lat)
                    for a in clusters[i]
                    for b in clusters[j]
                )
                if d < best_d:
                    best_i, best_j, best_d = i, j, d
        if best_d > threshold_km:
            break
        clusters[best_i].extend(clusters[best_j])
        del clusters[best_j]
    return clusters


def _cluster_center(cluster: list[PoiPoint]) -> tuple[float, float]:
    return (
        sum(p.lng for p in cluster) / len(cluster),
        sum(p.lat for p in cluster) / len(cluster),
    )


def _cluster_span_km(cluster: list[PoiPoint]) -> float:
    if len(cluster) <= 1:
        return 0.0
    span = 0.0
    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            span = max(
                span,
                _haversine_km(cluster[i].lng, cluster[i].lat, cluster[j].lng, cluster[j].lat),
            )
    return span


def _sort_clusters(clusters: list[list[PoiPoint]], hub: PoiPoint | None) -> list[list[PoiPoint]]:
    if not hub:
        return sorted(clusters, key=lambda c: -sum(p.rating for p in c) / len(c))

    def dist(c: list[PoiPoint]) -> float:
        cx, cy = _cluster_center(c)
        return _haversine_km(hub.lng, hub.lat, cx, cy)

    return sorted(clusters, key=dist)


def _merge_clusters_to_days(clusters: list[list[PoiPoint]], max_days: int) -> list[list[PoiPoint]]:
    merged = [list(c) for c in clusters]
    while len(merged) > max_days:
        best_i, best_j, best_d = -1, -1, float("inf")
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                d = min(
                    _haversine_km(a.lng, a.lat, b.lng, b.lat)
                    for a in merged[i]
                    for b in merged[j]
                )
                if d < best_d:
                    best_i, best_j, best_d = i, j, d
        merged[best_i].extend(merged[best_j])
        del merged[best_j]
    return merged


def _distribute_clusters_to_days(
    clusters: list[list[PoiPoint]],
    num_days: int,
) -> list[list[PoiPoint]]:
    """把地理片区映射到行程天数：片区多则合并，少则把同片区拆到多天。"""
    if num_days <= 0:
        return []
    if not clusters:
        return [[] for _ in range(num_days)]
    merged = _merge_clusters_to_days(clusters, min(len(clusters), num_days))
    if len(merged) == num_days:
        return merged
    if len(merged) == 1:
        chain = _nearest_neighbor_chain(merged[0])
        per_day: list[list[PoiPoint]] = [[] for _ in range(num_days)]
        for i, poi in enumerate(chain):
            per_day[i % num_days].append(poi)
        return per_day
    while len(merged) < num_days:
        merged.append([])
    return merged[:num_days]


def _is_remote_day_trip(cluster: list[PoiPoint], hub: PoiPoint | None) -> bool:
    if not cluster:
        return False
    if _cluster_span_km(cluster) >= GEO_CLUSTER_KM:
        return True
    if not hub:
        return False
    cx, cy = _cluster_center(cluster)
    return _haversine_km(hub.lng, hub.lat, cx, cy) >= GEO_CLUSTER_KM


def _assign_play_by_clusters(
    slot_keys: list[tuple[int, int]],
    clusters: list[list[PoiPoint]],
    pool: list[PoiPoint],
    hub: PoiPoint | None,
) -> dict[tuple[int, int], PoiPoint]:
    """按日分配玩点：一天一个地理片区，跨城远点单独成日且只排 1 个玩点。"""
    by_day: dict[int, list[tuple[int, int]]] = {}
    for key in slot_keys:
        by_day.setdefault(key[0], []).append(key)

    ranked_pool = sorted(pool, key=lambda p: (-p.rating, p.name))
    result: dict[tuple[int, int], PoiPoint] = {}
    trip_used: set[str] = set()

    for idx, day_i in enumerate(sorted(by_day.keys())):
        keys = by_day[day_i]
        cluster = _nearest_neighbor_chain(clusters[idx]) if idx < len(clusters) else []
        remote = _is_remote_day_trip(cluster, hub)
        max_from_cluster = 1 if remote else len(keys)
        day_used: set[str] = set()

        for j, key in enumerate(keys):
            poi: PoiPoint | None = None
            if j < max_from_cluster and j < len(cluster):
                poi = cluster[j]
            if poi and poi.id in day_used:
                poi = None
            if not poi:
                for candidate in ranked_pool:
                    if candidate.id not in day_used and candidate.id not in trip_used:
                        poi = candidate
                        break
            if not poi:
                for candidate in ranked_pool:
                    if candidate.id not in day_used:
                        poi = candidate
                        break
            if poi:
                result[key] = poi
                day_used.add(poi.id)
                trip_used.add(poi.id)
    return result


def _build_play_schedule(
    days: int,
    order: list[str],
    selected_play: list[PoiPoint],
    pool: list[PoiPoint],
) -> dict[tuple[int, int], PoiPoint]:
    slot_keys = _slot_keys_for_category(days, order, "玩")
    if not slot_keys:
        return {}
    num_days = len({k[0] for k in slot_keys})
    need = len(slot_keys)

    if selected_play:
        hub = selected_play[0]
        core = _expand_unique_candidates(selected_play, [], max(len(selected_play), need))
        clusters = _cluster_pois_by_distance(core)
        clusters = _sort_clusters(clusters, hub)
        clusters = _distribute_clusters_to_days(clusters, num_days)
        return _assign_play_by_clusters(slot_keys, clusters, pool, hub)

    candidates = _expand_unique_candidates(selected_play, pool, need)
    hub = candidates[0] if candidates else None
    clusters = _cluster_pois_by_distance(candidates)
    clusters = _sort_clusters(clusters, hub)
    clusters = _distribute_clusters_to_days(clusters, num_days)
    return _assign_play_by_clusters(slot_keys, clusters, pool, hub)


def _collect_fill_eat_candidates(
    session: dict[str, Any],
    pois: dict[str, list[PoiPoint]],
) -> list[PoiPoint]:
    """锚点周边填充推荐中的餐厅（玩锚点 + 住跟随时，吃由填充自动补足）。"""
    result: list[PoiPoint] = []
    seen: set[str] = set()
    for group in build_fill_picks(session):
        for pick in group.get("picks") or []:
            if pick.get("poi_type") != "吃":
                continue
            matched = _find_poi_in_pool(pois.get("吃", []), pick)
            if matched and matched.id not in seen:
                result.append(matched)
                seen.add(matched.id)
    return result


def _rank_eats_for_refs(
    pool: list[PoiPoint],
    refs: list[PoiPoint],
    *,
    exclude: set[str] | None = None,
) -> list[PoiPoint]:
    """按评分 + 与当日动线参考点的距离排序餐厅。"""
    excluded = exclude or set()

    def sort_key(e: PoiPoint) -> tuple:
        if not refs:
            return (-e.rating, e.name)
        min_dist = min(_haversine_km(r.lng, r.lat, e.lng, e.lat) for r in refs)
        return (-e.rating, min_dist, e.name)

    return [e for e in sorted(pool, key=sort_key) if e.id not in excluded]


def _build_eat_schedule(
    days: int,
    order: list[str],
    selected: list[PoiPoint],
    pool: list[PoiPoint],
    session: dict[str, Any],
    pois: dict[str, list[PoiPoint]],
    play_schedule: dict[tuple[int, int], PoiPoint],
    stay_schedule: dict[tuple[int, int], PoiPoint],
) -> dict[tuple[int, int], PoiPoint]:
    """吃：用户所选优先；否则用锚点周边填充 + 按日就近，同日/全程尽量不重复。"""
    slot_keys = _slot_keys_for_category(days, order, "吃")
    if not slot_keys or not pool:
        return {}

    fill_eats = _collect_fill_eat_candidates(session, pois)
    seen: set[str] = set()
    eat_pool: list[PoiPoint] = []
    for poi in selected + fill_eats + sorted(pool, key=lambda p: (-p.rating, p.name)):
        if poi.id not in seen:
            eat_pool.append(poi)
            seen.add(poi.id)

    by_day: dict[int, list[tuple[int, int]]] = {}
    for key in slot_keys:
        by_day.setdefault(key[0], []).append(key)

    result: dict[tuple[int, int], PoiPoint] = {}
    trip_used: set[str] = set()

    for day_i in sorted(by_day.keys()):
        refs: list[PoiPoint] = []
        for key, poi in play_schedule.items():
            if key[0] == day_i:
                refs.append(poi)
        for key, poi in stay_schedule.items():
            if key[0] == day_i:
                refs.append(poi)

        day_used: set[str] = set()
        ranked = _rank_eats_for_refs(eat_pool, refs, exclude=set())

        for key in by_day[day_i]:
            poi: PoiPoint | None = None
            for candidate in ranked:
                if candidate.id not in day_used and candidate.id not in trip_used:
                    poi = candidate
                    break
            if poi is None:
                for candidate in ranked:
                    if candidate.id not in day_used:
                        poi = candidate
                        break
            if poi:
                result[key] = poi
                day_used.add(poi.id)
                trip_used.add(poi.id)

    return result


def _parse_follow_pois(session: dict[str, Any], pois: dict[str, list[PoiPoint]]) -> list[PoiPoint]:
    spec = resolve_travel_mode(session)
    follow_type = spec.follow_type
    pool = pois.get(follow_type, [])
    result: list[PoiPoint] = []
    seen: set[str] = set()
    for item in session.get("selected_follow_pois") or []:
        if not isinstance(item, dict):
            continue
        matched = _find_poi_in_pool(pool, item)
        if matched and matched.id not in seen:
            result.append(matched)
            seen.add(matched.id)
    return result


def _build_fill_points(session: dict[str, Any], pois: dict[str, list[PoiPoint]]) -> list[PoiPoint]:
    points: list[PoiPoint] = []
    seen: set[str] = set()
    for group in build_fill_picks(session):
        for pick in group.get("picks") or []:
            cat = pick.get("poi_type") or "玩"
            matched = _find_poi_in_pool(pois.get(cat, []), pick)
            if matched and matched.id not in seen:
                points.append(matched)
                seen.add(matched.id)
    return points


def _resolve_poi(
    pool: list[PoiPoint],
    cat: str,
    day_index: int,
    slot: int,
    hotel: PoiPoint | None,
    eat: PoiPoint | None,
    play_schedule: dict[tuple[int, int], PoiPoint],
    stay_schedule: dict[tuple[int, int], PoiPoint],
    eat_schedule: dict[tuple[int, int], PoiPoint],
    fill_points: list[PoiPoint],
    fill_cursor: list[int],
) -> PoiPoint | None:
    key = (day_index + 1, slot)
    if cat == "住":
        if stay_schedule.get(key):
            return stay_schedule[key]
        return hotel
    if cat == "吃":
        if eat_schedule.get(key):
            return eat_schedule[key]
        if eat:
            return eat
    if cat == "玩":
        scheduled = play_schedule.get(key)
        if scheduled:
            return scheduled
    if fill_points:
        idx = fill_cursor[0] % len(fill_points)
        fill_cursor[0] += 1
        candidate = fill_points[idx]
        if candidate.poi_type == cat:
            return candidate
    return _pick_poi(pool, day_index, slot)


def build_flipbook_plan(
    session: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    use_cache: bool = True,
) -> dict[str, Any]:
    cache_key = session_plan_key(session)
    if use_cache:
        cached = _PLAN_CACHE.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SEC:
            return cached[1]

    slots = session.get("slots") or {}
    destination = slots.get("destination") or "重庆"
    days = resolve_plan_days(session)
    anchor = slots.get("anchor") or "玩"
    tags = resolve_profile_tags(list(slots.get("tags") or []))
    cover = _cover_meta(session)

    conn = _connect(db_path)
    try:
        user_tag = db_user_tag(tags[0]) if tags else "上班族"
        pois, traffic, matching_map = _load_city_bundle(conn, destination, user_tag)
        if not pois["玩"]:
            raise ValueError(f"暂无 {destination} 的 POI 数据")

        order = slot_order_for_session(session)
        selected_play, selected_hotel, selected_eat = _parse_selected_anchor_pois(session, pois)
        follow_pois = _parse_follow_pois(session, pois)
        spec = resolve_travel_mode(session)
        follow_stay = [p for p in follow_pois if p.poi_type == "住"]
        follow_eat = [p for p in follow_pois if p.poi_type == "吃"]
        follow_play = [p for p in follow_pois if p.poi_type == "玩"]

        hotel = selected_hotel or (follow_stay[0] if follow_stay else None) or (pois["住"][0] if pois["住"] else None)
        eat_anchor = selected_eat or (follow_eat[0] if follow_eat else None)
        play_selected = selected_play + [p for p in follow_play if p.id not in {x.id for x in selected_play}]

        play_schedule = _build_play_schedule(days, order, play_selected, pois["玩"])
        stay_candidates = follow_stay + ([selected_hotel] if selected_hotel else [])
        eat_list = follow_eat + ([eat_anchor] if eat_anchor else [])
        # 酒店优化先按玩点动线；吃在定好酒店后按玩+住就近填充
        stay_schedule = _build_fatigue_optimized_hotel_schedule(
            days,
            order,
            stay_candidates,
            pois["住"],
            play_schedule,
            {},
            traffic,
        )
        eat_schedule = _build_eat_schedule(
            days,
            order,
            eat_list,
            pois["吃"],
            session,
            pois,
            play_schedule,
            stay_schedule,
        )
        hotel_switches = _count_hotel_switches(stay_schedule)
        scheduled_play_ids = {p.id for p in play_schedule.values()}
        scheduled_eat_ids = {p.id for p in eat_schedule.values()}
        fill_points = [
            p
            for p in _build_fill_points(session, pois)
            if p.id not in scheduled_play_ids and p.id not in scheduled_eat_ids
        ]
        fill_eat_ids = {p.id for p in _collect_fill_eat_candidates(session, pois)}
        fill_cursor = [0]
        day_plans: list[dict[str, Any]] = []
        total_km = 0.0
        plan_day_metrics: list[PlanDayMetrics] = []

        for day_i in range(1, days + 1):
            timeline: list[dict[str, Any]] = []
            route: list[dict[str, Any]] = []
            prev: PoiPoint | None = None
            day_tran = 0.0
            day_attract = 0.0
            matching_scores: list[float] = []
            must_visits: list[MustVisitPoi] = []

            for time_label, slot_idx in DAY_SLOTS:
                if slot_idx >= len(order):
                    continue
                cat = order[slot_idx]
                poi = _resolve_poi(
                    pois[cat],
                    cat,
                    day_i - 1,
                    slot_idx,
                    hotel,
                    eat_anchor,
                    play_schedule,
                    stay_schedule,
                    eat_schedule,
                    fill_points,
                    fill_cursor,
                )
                if not poi:
                    continue

                tran_min, tran_factor, tran_mode = 0.0, 1.0, "步行"
                tran_cost = 0.0
                leg_km = 0.0
                if prev:
                    leg_km = _haversine_km(prev.lng, prev.lat, poi.lng, poi.lat)
                    total_km += leg_km
                    tran_min, tran_factor, tran_mode = _leg_tran(prev, poi, traffic)
                    tran_cost = calc_tran_cost(tran_min, tran_factor)

                attract_cost = 0.0
                if poi.poi_type == "玩":
                    matching = matching_map.get(poi.tier, 1.0)
                    ms = calc_matching_score(poi.rating, matching)
                    matching_scores.append(ms)
                    must_visits.append(MustVisitPoi(poi.name, ms))
                    attract_cost = calc_attract_cost(poi.attract_time, poi.attract_factor)

                day_tran += tran_cost
                day_attract += attract_cost

                if poi.poi_type == "住":
                    detail = "贴近今日动线 · 省力落脚"
                    if tran_min > 0:
                        detail = f"贴近今日动线 · {tran_mode} {int(tran_min)}min"
                elif tran_min > 0:
                    detail = f"{tran_mode} {int(tran_min)}min，消耗 {int(tran_cost)} 分"
                elif poi.poi_type == "玩":
                    detail = f"游玩约 {poi.attract_time:.0f}h，消耗 {int(attract_cost)} 分"
                elif poi.poi_type == "吃":
                    if poi.id in fill_eat_ids and not eat_anchor and not follow_eat:
                        detail = f"评分 {poi.rating:.1f} · 锚点周边填充 · {poi.cuisine_type or '本地风味'}"
                    else:
                        detail = f"评分 {poi.rating:.1f} · {poi.cuisine_type or '本地风味'}"
                else:
                    detail = "锚点「住」推荐"

                node: dict[str, Any] = {
                        "time": time_label,
                        "type": poi.poi_type,
                        "name": poi.name,
                        "poi_id": poi.id,
                        "detail": detail,
                        "tran_minutes": int(tran_min),
                        "tran_cost": round(tran_cost, 1),
                        "attract_cost": round(attract_cost, 1),
                        "lng": poi.lng,
                        "lat": poi.lat,
                        "tier": poi.tier if poi.poi_type == "玩" else None,
                        "open_time": poi.open_time if poi.poi_type == "玩" else None,
                        "ticket": poi.ticket_price if poi.poi_type == "玩" else None,
                        "cuisine": poi.cuisine_type if poi.poi_type == "吃" else None,
                    }
                if prev:
                    node["leg_id"] = f"d{day_i}-leg{len(timeline)}"
                    node["leg_distance_km"] = round(leg_km, 1)
                    node["tran_mode_db"] = tran_mode
                    node["tran_mode"] = tran_mode
                    node["tran_factor"] = tran_factor
                timeline.append(node)
                route.append({"name": poi.name, "lng": poi.lng, "lat": poi.lat, "type": poi.poi_type})
                prev = poi

            fatigue_index = calc_fatigue_index(
                [day_tran], [day_attract], luggage_count=0
            )
            plan_day_metrics.append(
                PlanDayMetrics(
                    day_index=day_i,
                    matching_scores=matching_scores,
                    must_visit_pois=must_visits,
                    tran_cost=day_tran,
                    attract_cost=day_attract,
                    fatigue_index=fatigue_index,
                )
            )
            day_plans.append(
                {
                    "day_index": day_i,
                    "timeline": timeline,
                    "route": route,
                    "day_fatigue": round(fatigue_index, 1),
                    "day_km": round(
                        sum(
                            _haversine_km(
                                route[i]["lng"],
                                route[i]["lat"],
                                route[i + 1]["lng"],
                                route[i + 1]["lat"],
                            )
                            for i in range(len(route) - 1)
                        ),
                        1,
                    ),
                    "ready": True,
                }
            )
    finally:
        conn.close()

    metrics = PlanMetrics(
        destination=destination,
        days=days,
        anchor=anchor,
        tags=tags,
        day_metrics=plan_day_metrics,
        luggage_count=hotel_switches,
    )
    attach_day_diagnoses(day_plans, metrics)

    cover["total_commute_km"] = round(total_km, 1)
    plan: dict[str, Any] = {
        "shell": False,
        "cover": cover,
        "days": day_plans,
        "back": {
            "pdf_label": "下载 PDF 路书",
            "share_label": "生成长图分享",
            "share_url": f"/archor/p6.html?city={destination}",
        },
        "build_steps": [{"id": s["id"], "label": s["label"], "done": True} for s in FILL_STEPS],
    }

    prefs = resolve_session_transport_preferences(session)
    draft_legs = extract_transport_legs(plan, tags, preferred_modes=prefs)
    mode_by_leg = merge_transport_selections(draft_legs, session.get("transport_modes"))
    plan = apply_transport_modes(plan, mode_by_leg)
    plan["transport_legs"] = refresh_leg_costs(draft_legs, mode_by_leg)
    plan["transport_modes"] = mode_by_leg
    plan["transport_confirmed"] = bool(session.get("transport_confirmed", True))
    plan["transport_preferences"] = prefs
    plan["transport_preference_label"] = describe_transport_preferences(prefs)
    plan["travel_mode"] = resolve_travel_mode(session).code
    plan["selected_anchor_pois"] = session.get("selected_anchor_pois") or []
    plan["selected_follow_pois"] = session.get("selected_follow_pois") or []
    if session.get("selected_anchor_poi"):
        plan["selected_anchor_poi"] = session.get("selected_anchor_poi")

    _PLAN_CACHE[cache_key] = (time.time(), plan)
    return plan


def is_plan_cached(session: dict[str, Any]) -> bool:
    key = session_plan_key(session)
    cached = _PLAN_CACHE.get(key)
    return bool(cached and (time.time() - cached[0]) < _CACHE_TTL_SEC)
