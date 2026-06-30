"""收束后用户修改意图 → 局部调整槽位/疲劳参数。"""

from __future__ import annotations

import re

from anchor.slots import Slots
from anchor.tag_mapping import has_low_stamina_tag

PACE_LABELS: dict[str, str] = {
    "normal": "标准节奏，动线顺路优先",
    "relaxed": "轻松节奏，减少折返、多留休息",
    "compact": "紧凑节奏，尽量多逛",
}


def infer_pace_modifier(message: str, current: str = "normal") -> str:
    text = message.strip()
    if re.search(r"太累|轻松|别太累|减累|少走|慢点|躺平|不想动", text):
        return "relaxed"
    if re.search(r"紧凑|多玩|多逛|加点|再多", text):
        return "compact"
    return current


def describe_plan_adjustment(pace_modifier: str) -> str:
    return PACE_LABELS.get(pace_modifier, PACE_LABELS["normal"])


def apply_modification_hints(message: str, slots: Slots) -> Slots:
    """修改意图不写入 tags；anchor 保持 吃/住/玩 大类。"""
    return slots


def is_modification_intent(message: str) -> bool:
    text = message.strip()
    patterns = (
        r"太累|轻松|别太累|减累|少走|慢点|躺平",
        r"太贵|便宜|预算|省钱|性价比",
        r"换(?:个|个)?|改成|不要|换个",
        r"紧凑|多玩|多逛|加点",
        r"改(?:一下|改)|调整|少玩|缩短|延长|\d+\s*天",
    )
    return any(re.search(p, text) for p in patterns)


def care_note_for_tags(tags: list[str]) -> str:
    if has_low_stamina_tag(tags):
        return "我会特别帮你控节奏、多留休息，照顾同行人的体力。"
    return ""
