"""P1 五种模式 → 锚点 / 跟随 / 日槽位吃住玩顺序。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# P1 capsule data-mode → 旅行模式
TRAVEL_MODE_BY_P1: dict[str, str] = {
    "ROUTE": "play_drive",
    "FOOD": "food_drive",
    "FILL": "stay_drive",
    "EVENT": "route_light",
    "BUDGET": "budget_drive",
}

ANCHOR_BY_TRAVEL_MODE: dict[str, str] = {
    "play_drive": "玩",
    "food_drive": "吃",
    "stay_drive": "住",
    "route_light": "玩",
    "budget_drive": "吃",
}


@dataclass(frozen=True)
class TravelModeSpec:
    code: str
    name: str
    anchor: str
    follow_type: str
    slot_order: tuple[str, ...]
    tagline: str


TRAVEL_MODES: dict[str, TravelModeSpec] = {
    "play_drive": TravelModeSpec(
        code="play_drive",
        name="景点驱动",
        anchor="玩",
        follow_type="住",
        slot_order=("玩", "住", "吃", "玩", "吃"),
        tagline="以景点定盘，再安排住与吃",
    ),
    "food_drive": TravelModeSpec(
        code="food_drive",
        name="美食驱动",
        anchor="吃",
        follow_type="玩",
        slot_order=("吃", "玩", "吃", "住", "玩"),
        tagline="先锁定味蕾，再顺路逛与住",
    ),
    "stay_drive": TravelModeSpec(
        code="stay_drive",
        name="住宿驱动",
        anchor="住",
        follow_type="吃",
        slot_order=("住", "玩", "吃", "玩", "吃"),
        tagline="以落脚点为中心，辐射玩与吃",
    ),
    "route_light": TravelModeSpec(
        code="route_light",
        name="顺路驱动",
        anchor="玩",
        follow_type="吃",
        slot_order=("玩", "吃", "住"),
        tagline="时间紧也能玩得省路",
    ),
    "budget_drive": TravelModeSpec(
        code="budget_drive",
        name="均衡驱动",
        anchor="玩",
        follow_type="住",
        slot_order=("玩", "吃", "住", "吃", "玩"),
        tagline="玩住吃均衡，不押单点",
    ),
}


def resolve_travel_mode(session: dict[str, Any]) -> TravelModeSpec:
    slots = session.get("slots") or {}
    anchor = slots.get("anchor")
    code = session.get("travel_mode")
    if not code:
        p1 = str(session.get("p1_mode") or "")
        code = TRAVEL_MODE_BY_P1.get(p1)
    if code and code in TRAVEL_MODES:
        spec = TRAVEL_MODES[code]
        if not anchor or spec.anchor == anchor:
            return spec
    for spec in TRAVEL_MODES.values():
        if spec.anchor == anchor:
            return spec
    return TRAVEL_MODES["play_drive"]


def slot_order_for_session(session: dict[str, Any]) -> list[str]:
    spec = resolve_travel_mode(session)
    return list(spec.slot_order)


def resolve_plan_days(session: dict[str, Any]) -> int:
    """EVENT / 顺路轻量模式只排 1 天短时动线；其余按用户天数。"""
    slots = session.get("slots") or {}
    days = int(slots.get("days") or 3)
    spec = resolve_travel_mode(session)
    if spec.code == "route_light":
        return 1
    return max(days, 1)
