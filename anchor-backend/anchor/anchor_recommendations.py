"""收束阶段：锁定第一锚点 + 具体 POI 推荐（含理由、评分、时间）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from anchor.poi_repository import (
    Attraction,
    Hotel,
    Restaurant,
    get_attractions_by_city,
    get_hotels_by_city,
    get_matching_tag,
    get_restaurants_by_city,
)
from anchor.poi_sketches import sketch_url
from anchor.recommender import calc_matching_score
from anchor.slots import Slots
from anchor.tag_mapping import db_user_tag, has_low_stamina_tag, resolve_profile_tags

ANCHOR_FOCUS: dict[str, str] = {
    "玩": "逛景点、顺路游玩",
    "住": "住得舒服、一住到底",
    "吃": "地道风味、围绕美食排行程",
}

TIER_VISIT_HINT: dict[str, str] = {
    "特级": "体力消耗偏高，建议预留充足时间并穿插休息",
    "高级": "内容密度大，可按展馆/街区拆成上下午",
    "中级": "步行强度适中，适合半天串联",
    "低级": "轻松打卡，1–2 小时即可",
}

MEAL_SLOTS = ("午餐 11:30–13:30", "晚餐 18:00–20:30", "下午茶 15:00–17:00")


@dataclass
class AnchorPoiPick:
    rank: int
    poi_id: str
    name: str
    poi_type: str
    rating: float
    visit_time: str
    reason: str
    matching_score: float | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.extra and self.extra.get("sketch_image"):
            data["sketch_image"] = self.extra["sketch_image"]
        if self.extra and self.extra.get("intro"):
            data["intro"] = self.extra["intro"]
        if not data.get("extra"):
            data.pop("extra", None)
        return data


@dataclass
class AnchorRecommendationBundle:
    anchor: str
    anchor_focus: str
    destination: str
    picks: list[AnchorPoiPick]

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor,
            "anchor_focus": self.anchor_focus,
            "destination": self.destination,
            "picks": [p.to_dict() for p in self.picks],
            "text": format_anchor_recommendations(self),
        }


def _profile_phrase(tags: list[str]) -> str:
    resolved = resolve_profile_tags(tags)
    return resolved[0] if resolved else "您的出行"


def _user_tag_for_matching(tags: list[str]) -> str:
    resolved = resolve_profile_tags(tags)
    if not resolved:
        return "上班族"
    return db_user_tag(resolved[0])


def _visit_time_attraction(poi: Attraction) -> str:
    hours = f"约 {poi.attract_time:.1f} 小时"
    if poi.open_time:
        return f"{hours}（开放 {poi.open_time}）"
    return hours


def _play_intro(poi: Attraction) -> str:
    if poi.brief_intro:
        return poi.brief_intro
    return f"{poi.name}，{poi.city}热门景点。"


def _reason_play(poi: Attraction, matching_score: float, tags: list[str]) -> str:
    base = _play_intro(poi).rstrip("。")
    parts = [base]
    if poi.ticket_price:
        parts.append(f"门票 {poi.ticket_price}")
    tier_hint = TIER_VISIT_HINT.get(poi.attract_tier)
    if tier_hint:
        parts.append(tier_hint)
    return "，".join(parts) + "。"


def _reason_hotel(poi: Hotel, tags: list[str], days: int | None) -> str:
    profile = _profile_phrase(tags)
    star = f"{poi.star_level} · " if poi.star_level else ""
    price = f"参考价 {poi.price_range}" if poi.price_range else "口碑稳定"
    nights = "按每日景点就近安排" if days and days > 1 else "作为首日落脚点"
    if has_low_stamina_tag(tags):
        comfort = "优先少奔波，仅在明显更近时才建议换房"
    else:
        comfort = "在少换房与少赶路之间取更省力的一侧"
    return f"为{profile}优选：{star}{price}；{nights}，{comfort}。"


def _reason_eat(poi: Restaurant, tags: list[str], meal_slot: str) -> str:
    profile = _profile_phrase(tags)
    cuisine = poi.cuisine_type or "本地风味"
    price = f"，人均 {poi.price_range}" if poi.price_range else ""
    if has_low_stamina_tag(tags):
        pace = "口味稳妥、等位压力相对小"
    else:
        pace = "代表性强，适合作为「吃」锚点的首发站"
    return f"{meal_slot}推荐「{cuisine}」{price}；贴合{profile}的味蕾偏好，{pace}。"


def _rank_attractions(
    pois: list[Attraction],
    user_tag: str,
    tags: list[str],
) -> list[tuple[Attraction, float]]:
    scored: list[tuple[Attraction, float]] = []
    for poi in pois:
        tag_coef = get_matching_tag(user_tag, poi.attract_tier)
        if has_low_stamina_tag(tags) and poi.attract_tier == "特级":
            tag_coef *= 0.35
        elif has_low_stamina_tag(tags) and poi.attract_tier == "高级":
            tag_coef *= 0.75
        ms = calc_matching_score(poi.rating, tag_coef)
        scored.append((poi, ms))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _pick_play(slots: Slots, user_tag: str, *, limit: int) -> list[AnchorPoiPick]:
    pois = get_attractions_by_city(slots.destination or "", limit=20)
    ranked = _rank_attractions(pois, user_tag, slots.tags)
    picks: list[AnchorPoiPick] = []
    for i, (poi, ms) in enumerate(ranked[:limit], start=1):
        picks.append(
            AnchorPoiPick(
                rank=i,
                poi_id=poi.id,
                name=poi.name,
                poi_type="玩",
                rating=poi.rating,
                visit_time=_visit_time_attraction(poi),
                reason=_reason_play(poi, ms, slots.tags),
                matching_score=round(ms, 1),
                extra={
                    "tier": poi.attract_tier,
                    "ticket": poi.ticket_price,
                    "sketch_image": sketch_url(poi.id),
                    "intro": _play_intro(poi),
                },
            )
        )
    return picks


def _pick_stay(slots: Slots, *, limit: int) -> list[AnchorPoiPick]:
    pois = get_hotels_by_city(slots.destination or "", limit=20)
    picks: list[AnchorPoiPick] = []
    for i, poi in enumerate(pois[:limit], start=1):
        picks.append(
            AnchorPoiPick(
                rank=i,
                poi_id=poi.id,
                name=poi.name,
                poi_type="住",
                rating=poi.rating,
                visit_time=(
                    f"建议连续入住 {slots.days} 晚"
                    if slots.days and slots.days > 1
                    else "建议全程以此为落脚点"
                ),
                reason=_reason_hotel(poi, slots.tags, slots.days),
                matching_score=round(poi.rating * 20, 1),
                extra={"star_level": poi.star_level, "price_range": poi.price_range, "sketch_image": sketch_url(poi.id)},
            )
        )
    return picks


def _pick_eat(slots: Slots, *, limit: int) -> list[AnchorPoiPick]:
    pois = get_restaurants_by_city(slots.destination or "", limit=20)
    picks: list[AnchorPoiPick] = []
    for i, poi in enumerate(pois[:limit], start=1):
        meal_slot = MEAL_SLOTS[(i - 1) % len(MEAL_SLOTS)]
        picks.append(
            AnchorPoiPick(
                rank=i,
                poi_id=poi.id,
                name=poi.name,
                poi_type="吃",
                rating=poi.rating,
                visit_time=f"{meal_slot} · 用餐约 1–1.5 小时",
                reason=_reason_eat(poi, slots.tags, meal_slot),
                matching_score=round(poi.rating * 20, 1),
                extra={"cuisine": poi.cuisine_type, "price_range": poi.price_range, "sketch_image": sketch_url(poi.id)},
            )
        )
    return picks


def build_anchor_recommendations(
    slots: Slots,
    *,
    limit: int = 3,
) -> AnchorRecommendationBundle | None:
    if not slots.destination or not slots.anchor:
        return None

    anchor = slots.anchor
    user_tag = _user_tag_for_matching(slots.tags)

    if anchor == "玩":
        picks = _pick_play(slots, user_tag, limit=limit)
    elif anchor == "住":
        picks = _pick_stay(slots, limit=limit)
    elif anchor == "吃":
        picks = _pick_eat(slots, limit=limit)
    else:
        return None

    if not picks:
        return None

    return AnchorRecommendationBundle(
        anchor=anchor,
        anchor_focus=ANCHOR_FOCUS.get(anchor, anchor),
        destination=slots.destination,
        picks=picks,
    )


def format_anchor_recommendations(bundle: AnchorRecommendationBundle) -> str:
    type_label = {"玩": "景点", "住": "酒店", "吃": "餐厅"}.get(bundle.anchor, "推荐")

    lines = [
        f"【第一锚点已锁定】{bundle.anchor} · {bundle.anchor_focus}",
        f"基于 {bundle.destination} POI 库，为你优选 {len(bundle.picks)} 个首发{type_label}：",
        "",
    ]
    for pick in bundle.picks:
        score_part = f" · 综合分 {pick.matching_score}" if pick.matching_score is not None else ""
        lines.extend(
            [
                f"{pick.rank}. {pick.name}",
                f"   · 评分 {pick.rating:.1f}{score_part} · {pick.visit_time}",
                f"   · 简介：{pick.extra.get('intro') if pick.extra and pick.extra.get('intro') else pick.reason}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def suggest_anchor_recommendations(slots: Slots, *, limit: int = 3) -> str | None:
    """对话收束用：返回格式化推荐文案。"""
    bundle = build_anchor_recommendations(slots, limit=limit)
    if not bundle:
        return None
    return format_anchor_recommendations(bundle)
