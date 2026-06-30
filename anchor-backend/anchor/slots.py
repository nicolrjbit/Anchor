"""槽位模型与合并逻辑。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from anchor.states import REQUIRED_SLOTS
from anchor.tag_mapping import has_profile_tag, resolve_profile_tags, sanitize_profile_tags
from anchor.transport_mapping import (
    normalize_transport_preferences,
    transport_is_satisfied,
)

ANCHOR_CATEGORIES = frozenset({"吃", "住", "玩"})

SUPPORTED_CITIES = frozenset({"北京", "南京", "重庆", "新疆", "成都", "西安"})

DESTINATION_ALIASES: dict[str, str] = {
    "北京市": "北京",
    "南京市": "南京",
    "重庆市": "重庆",
    "乌鲁木齐": "新疆",
    "乌鲁木齐市": "新疆",
}

MODE_ANCHOR: dict[str, str] = {
    "ROUTE": "玩",
    "EVENT": "玩",
    "FOOD": "吃",
    "FILL": "住",
    "RISK": "玩",
}

FOOD_HINT_RE = re.compile(
    r"吃|火锅|小面|板鸭|烤鸭|烧烤|串串|江湖菜|小吃|早茶|烤羊肉串|美食|寻味"
)
STAY_HINT_RE = re.compile(r"酒店|住宿|住在|订在|周边|附近|一带|区域|解放碑|新街口")
PLAY_HINT_RE = re.compile(
    r"玩|逛|游|景点|打卡|顺路|折返|冤枉路|游览|行程|短途|必去|故宫|洪崖洞|"
    r"紫金山|夫子庙|博物馆|博物院|漫步|走走"
)


def infer_anchor_category(
    raw: str | None = None,
    *,
    mode: str | None = None,
    text: str | None = None,
) -> str | None:
    """锚点 canonical 值只能是 吃 / 住 / 玩。"""
    if raw and raw.strip() in ANCHOR_CATEGORIES:
        return raw.strip()

    sources = " ".join(s for s in (raw, text) if s).strip()
    if sources:
        if mode == "FOOD" and FOOD_HINT_RE.search(sources):
            return "吃"
        if mode == "FILL" and STAY_HINT_RE.search(sources):
            return "住"
        if mode in ("ROUTE", "EVENT", "RISK") and PLAY_HINT_RE.search(sources):
            return "玩"
        if STAY_HINT_RE.search(sources):
            return "住"
        if FOOD_HINT_RE.search(sources):
            return "吃"
        if PLAY_HINT_RE.search(sources):
            return "玩"

    if mode and mode in MODE_ANCHOR:
        return MODE_ANCHOR[mode]
    return None


def normalize_anchor(
    raw: str | None,
    *,
    mode: str | None = None,
    text: str | None = None,
) -> str | None:
    return infer_anchor_category(raw, mode=mode, text=text)


def normalize_destination(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    city = str(raw).strip()
    return DESTINATION_ALIASES.get(city, city)


def destination_is_supported(raw: str | None) -> bool:
    city = normalize_destination(raw)
    return city in SUPPORTED_CITIES if city else False


def supported_cities_label() -> str:
    return "、".join(sorted(SUPPORTED_CITIES))


def anchor_is_satisfied(anchor: str | None) -> bool:
    return anchor in ANCHOR_CATEGORIES


def prefer_anchor(
    existing: str | None,
    incoming: str | None,
    *,
    mode: str | None = None,
    text: str | None = None,
) -> str | None:
    normalized_in = normalize_anchor(incoming, mode=mode, text=text)
    normalized_ex = normalize_anchor(existing, mode=mode)
    if normalized_in and normalized_ex:
        if mode and MODE_ANCHOR.get(mode) == normalized_ex:
            return normalized_ex
        return normalized_in
    return normalized_in or normalized_ex


@dataclass
class Slots:
    destination: str | None = None
    days: int | None = None
    anchor: str | None = None
    tags: list[str] = field(default_factory=list)
    transport_preferences: list[str] = field(default_factory=list)

    def missing(self, *, mode: str | None = None) -> list[str]:
        """对话采集缺项；P1 模式已定锚点大类时不追问 anchor。"""
        missing: list[str] = []
        if not destination_is_supported(self.destination):
            missing.append("destination")
        if self.days is None or self.days <= 0:
            missing.append("days")
        if not anchor_is_satisfied(self.anchor):
            if not (mode and mode in MODE_ANCHOR):
                missing.append("anchor")
        if not has_profile_tag(self.tags):
            missing.append("tags")
        if not transport_is_satisfied(self.transport_preferences):
            missing.append("transport")
        return missing

    def is_complete(self, *, mode: str | None = None) -> bool:
        return len(self.missing(mode=mode)) == 0

    def is_complete_for_fatigue(self, *, mode: str | None = None) -> bool:
        """劳累度预演不要求已采集出行方式。"""
        return not any(m for m in self.missing(mode=mode) if m != "transport")

    def merge(self, patch: dict[str, Any], *, mode: str | None = None) -> Slots:
        """只覆盖 patch 中非空字段，tags 做并集去重。"""
        raw_dest = patch.get("destination") or self.destination
        destination = normalize_destination(raw_dest) if raw_dest else None
        days = patch.get("days") if patch.get("days") is not None else self.days
        anchor = prefer_anchor(
            self.anchor,
            patch.get("anchor"),
            mode=mode or patch.get("_mode"),
            text=patch.get("_text") or patch.get("anchor"),
        )

        tags = list(self.tags)
        incoming = patch.get("tags")
        if incoming:
            if isinstance(incoming, str):
                incoming = [incoming]
            tags = resolve_profile_tags(
                tags + [str(t).strip() for t in incoming if str(t).strip()]
            )

        tags = sanitize_profile_tags(tags)

        transport_preferences = normalize_transport_preferences(self.transport_preferences)
        if patch.get("transport_preferences") is not None:
            raw_tp = patch.get("transport_preferences")
            if isinstance(raw_tp, str):
                raw_list = [raw_tp]
            elif isinstance(raw_tp, list):
                raw_list = raw_tp
            else:
                raw_list = []
            incoming = normalize_transport_preferences(raw_list)
            if incoming:
                transport_preferences = incoming

        return Slots(
            destination=destination,
            days=int(days) if days is not None else None,
            anchor=anchor,
            tags=tags,
            transport_preferences=transport_preferences,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "days": self.days,
            "anchor": self.anchor,
            "tags": self.tags,
            "transport_preferences": self.transport_preferences,
        }


def slot_labels() -> dict[str, str]:
    return {
        "destination": "目的地（城市）",
        "days": "出行天数",
        "anchor": "锚点（吃 / 住 / 玩）",
        "tags": "用户画像（九个标准标签之一）",
        "transport": "出行方式偏好（如地铁+步行、自驾/租车）",
    }
