"""城市游玩推荐 — 优先读 POI 库，无库时用静态兜底。"""

from __future__ import annotations

from anchor.slots import Slots
from anchor.tag_mapping import has_low_stamina_tag, resolve_profile_tags

CITY_PLAY_ROUTES: dict[str, list[str]] = {
    "重庆": [
        "解放碑 → 洪崖洞 → 千厮门大桥（夜景一线，少折返）",
        "李子坝轻轨穿楼 → 鹅岭二厂（轻轨动线顺）",
        "磁器口古镇 → 渣滓洞（西线可串）",
    ],
    "北京": [
        "天安门 → 故宫 → 什刹海（中轴顺路）",
        "天坛 → 前门大街（南城一线）",
    ],
    "南京": [
        "夫子庙 → 老门东 → 总统府（城南顺路）",
        "玄武湖 → 南京博物院（城东一线）",
    ],
    "新疆": [
        "国际大巴扎 → 新疆博物馆（市区顺路）",
        "红山公园 → 友好商圈（乌鲁木齐）",
    ],
}


def suggest_play_routes(slots: Slots, *, limit: int = 3) -> str | None:
    if not slots.destination or slots.anchor == "吃":
        return None

    chains: list[str] = []
    try:
        from anchor.poi_repository import get_route_chains

        chains = get_route_chains(slots.destination, max_hops=limit)
    except FileNotFoundError:
        pass

    if not chains:
        chains = CITY_PLAY_ROUTES.get(slots.destination, [])[:limit]

    if not chains:
        return None

    if has_low_stamina_tag(slots.tags):
        profiles = resolve_profile_tags(slots.tags)
        note = f"（已按{profiles[0]}偏好筛选轻松动线）" if profiles else "（已按轻松节奏筛选）"
    else:
        note = "（按交通段顺路串联）"

    lines = "\n".join(f"- {c}" for c in chains[:limit])
    return f"顺路游玩建议{note}：\n{lines}"
