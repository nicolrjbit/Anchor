"""POI 间出行方式推荐与方案应用。"""

from __future__ import annotations

from typing import Any

from anchor.recommender import calc_tran_cost
from anchor.tag_mapping import has_low_stamina_tag
from anchor.transport_mapping import describe_transport_preferences

TRANSPORT_MODES: tuple[str, ...] = ("公交", "地铁", "骑行", "步行", "自驾")

MODE_FACTOR: dict[str, float] = {
    "公交": 1.15,
    "地铁": 1.2,
    "骑行": 1.6,
    "步行": 2.0,
    "自驾": 1.0,
    # 兼容旧数据
    "汽车": 1.0,
}

MODE_PROFILE: dict[str, dict[str, str]] = {
    "公交": {
        "pros": "覆盖面广、费用低，适合中等距离",
        "cons": "受路况与站点影响，高峰可能较慢",
    },
    "地铁": {
        "pros": "准点、避堵，跨区移动效率高",
        "cons": "要进出站，很近的路段反而折腾",
    },
    "骑行": {
        "pros": "灵活穿街走巷，中短距不堵",
        "cons": "需体力，坡道/天气要留意",
    },
    "步行": {
        "pros": "零换乘，1 公里内往往最快",
        "cons": "距离一长就费腿，带行李不友好",
    },
    "自驾": {
        "pros": "门到门、省力，远距或带老人孩子合适",
        "cons": "停车与拥堵成本，市中心未必划算",
    },
}

MODE_HINT: dict[str, str] = {
    "公交": "公交线路顺路，花费可控",
    "地铁": "城市动线常用，避开路面拥堵",
    "骑行": "距离适中时灵活，注意体力消耗",
    "步行": "短距离顺路串联，零换乘",
    "自驾": "省力省时，适合带行李或陪长辈",
    "汽车": "省力省时，适合带行李或陪长辈",
}


def transport_mode_catalog() -> list[dict[str, str]]:
    return [
        {"mode": m, "pros": MODE_PROFILE[m]["pros"], "cons": MODE_PROFILE[m]["cons"]}
        for m in TRANSPORT_MODES
    ]


def recommend_mode(
    *,
    distance_km: float,
    db_mode: str | None,
    tags: list[str],
    from_type: str,
    to_type: str,
    preferred_modes: list[str] | None = None,
) -> tuple[str, str]:
    """返回 (推荐方式, 推荐理由)。"""
    low_stamina = has_low_stamina_tag(tags)
    cross_hotel = {from_type, to_type} == {"玩", "住"} or {from_type, to_type} == {"吃", "住"}

    prefs = [m for m in (preferred_modes or []) if m in MODE_FACTOR]
    pref_label = describe_transport_preferences(prefs) if prefs else ""
    if prefs:
        mode = _pick_from_preferences(prefs, distance_km, low_stamina, cross_hotel)
        hint = MODE_HINT.get(mode, MODE_PROFILE.get(mode, {}).get("pros", ""))
        if distance_km < 0.6 and mode in ("地铁", "公交"):
            return (
                "步行",
                f"这段只有约 {int(distance_km * 1000)} 米，步行比{pref_label or mode}更省事",
            )
        lead = f"按你希望的{pref_label}" if pref_label else "按你的出行偏好"
        return mode, f"{lead}，这段推荐{mode}（{hint}）"

    if db_mode:
        mapped = "自驾" if db_mode == "汽车" else db_mode
        if mapped in MODE_FACTOR:
            if distance_km < 0.6 and mapped in ("地铁", "公交"):
                return "步行", "距离很近，步行比轨道交通更划算"
            hint = MODE_HINT.get(mapped, "与路况数据一致")
            if cross_hotel and low_stamina and mapped == "步行" and distance_km > 1.2:
                return "公交", "景点与酒店切换且距离偏长，公交比步行更省体力"
            return mapped, f"动线库推荐{mapped}，{hint}"

    if distance_km < 0.5:
        mode = "步行"
    elif distance_km < 1.0:
        mode = "步行" if not low_stamina else "公交"
    elif distance_km >= 8:
        mode = "自驾"
    elif distance_km >= 3:
        mode = "地铁" if not low_stamina else "公交"
    elif distance_km >= 1.2:
        mode = "公交" if cross_hotel else ("骑行" if not low_stamina else "公交")
    else:
        mode = "步行" if not low_stamina or distance_km < 0.8 else "公交"

    if cross_hotel and low_stamina and mode in ("骑行", "步行") and distance_km > 1.0:
        mode = "公交"

    reason = MODE_HINT.get(mode, "综合距离与画像推荐")
    if cross_hotel:
        type_label = {"玩": "景点", "住": "酒店", "吃": "餐厅"}
        reason = (
            f"{type_label.get(from_type, from_type)}→{type_label.get(to_type, to_type)}切换，"
            f"{reason}"
        )
    return mode, reason


def _pick_from_preferences(
    prefs: list[str],
    distance_km: float,
    low_stamina: bool,
    cross_hotel: bool,
) -> str:
    if prefs == ["自驾"] or (len(prefs) == 1 and prefs[0] == "自驾"):
        if distance_km < 0.35:
            return "步行"
        return "自驾"
    if distance_km < 0.5:
        return "步行" if "步行" in prefs else prefs[0]
    if distance_km < 0.8 and "步行" in prefs:
        return "步行"
    for mode in prefs:
        if mode == "步行" and distance_km > 2.5:
            continue
        if mode == "骑行" and (distance_km > 3 or low_stamina):
            continue
        if mode in ("地铁", "公交") and distance_km < 0.4:
            continue
        if cross_hotel and low_stamina and mode in ("骑行", "步行") and distance_km > 1.2:
            continue
        return mode
    return prefs[0]


def extract_transport_legs(
    plan: dict[str, Any],
    tags: list[str],
    preferred_modes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """从路书 timeline 提取需确认的出行段。"""
    legs: list[dict[str, Any]] = []
    for day in plan.get("days") or []:
        timeline = day.get("timeline") or []
        for idx in range(1, len(timeline)):
            prev = timeline[idx - 1]
            curr = timeline[idx]
            if not prev.get("poi_id") or not curr.get("poi_id"):
                continue
            leg_id = str(curr.get("leg_id") or "")
            if not leg_id:
                continue
            tran_min = float(curr.get("tran_minutes") or 0)
            distance_km = float(curr.get("leg_distance_km") or 0)
            db_mode = curr.get("tran_mode_db")
            recommended, reason = recommend_mode(
                distance_km=distance_km,
                db_mode=str(db_mode) if db_mode else None,
                tags=tags,
                from_type=str(prev.get("type") or ""),
                to_type=str(curr.get("type") or ""),
                preferred_modes=list(preferred_modes or []),
            )
            legs.append(
                {
                    "leg_id": leg_id,
                    "day_index": day["day_index"],
                    "from_name": prev.get("name"),
                    "from_type": prev.get("type"),
                    "to_name": curr.get("name"),
                    "to_type": curr.get("type"),
                    "distance_km": round(distance_km, 1),
                    "tran_minutes": int(tran_min),
                    "recommended_mode": recommended,
                    "selected_mode": recommended,
                    "tran_factor": MODE_FACTOR[recommended],
                    "tran_cost": round(calc_tran_cost(tran_min, MODE_FACTOR[recommended]), 1),
                    "reason": reason,
                    "cross_switch": prev.get("type") != curr.get("type"),
                }
            )
    return legs


def apply_transport_modes(
    plan: dict[str, Any],
    mode_by_leg: dict[str, str],
) -> dict[str, Any]:
    """按用户选择重算各段 tran_cost 并更新 timeline。"""
    if not mode_by_leg:
        return plan

    for day in plan.get("days") or []:
        day_tran = 0.0
        for node in day.get("timeline") or []:
            leg_id = node.get("leg_id")
            if not leg_id or leg_id not in mode_by_leg:
                continue
            mode = mode_by_leg[leg_id]
            if mode not in MODE_FACTOR:
                continue
            factor = MODE_FACTOR[mode]
            tran_min = float(node.get("tran_minutes") or 0)
            tran_cost = calc_tran_cost(tran_min, factor) if tran_min > 0 else 0.0
            node["tran_mode"] = mode
            node["tran_factor"] = factor
            node["tran_cost"] = round(tran_cost, 1)
            if tran_min > 0:
                if node.get("type") == "住":
                    node["detail"] = f"贴近今日动线 · {mode} {int(tran_min)}min"
                else:
                    node["detail"] = f"{mode} {int(tran_min)}min，消耗 {int(tran_cost)} 分"
            day_tran += tran_cost
        if day.get("timeline"):
            day["day_tran_cost"] = round(day_tran, 1)
    return plan


def merge_transport_selections(
    legs: list[dict[str, Any]],
    overrides: dict[str, str] | None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for leg in legs:
        leg_id = leg["leg_id"]
        mode = (overrides or {}).get(leg_id) or leg.get("selected_mode") or leg["recommended_mode"]
        if mode in MODE_FACTOR:
            out[leg_id] = mode
    return out


def refresh_leg_costs(legs: list[dict[str, Any]], mode_by_leg: dict[str, str]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for leg in legs:
        mode = mode_by_leg.get(leg["leg_id"], leg["recommended_mode"])
        factor = MODE_FACTOR.get(mode, 1.0)
        tran_min = float(leg.get("tran_minutes") or 0)
        item = dict(leg)
        item["selected_mode"] = mode
        item["tran_factor"] = factor
        item["tran_cost"] = round(calc_tran_cost(tran_min, factor), 1) if tran_min else 0.0
        updated.append(item)
    return updated
