"""对话侧劳累度预计算公式（与路书 POI fatigue_index 刻度分离）。

    预估劳累度 = (锚点体能系数 × 天数衰减系数 + 节奏标签加成) × pace_modifier

    天数衰减系数 = 1 + (days - 1) × 0.12

    用户体能上限(锚点刻度) = POI 画像上限 / POI_TO_ANCHOR_CAPACITY_SCALE

    展示分 = clamp(预估劳累度 / 用户体能上限 × 100, 1, 99)

    hasConflict = 语义冲突（低体力 + 高体能锚点）或 预估劳累度 > 用户体能上限

POI 画像上限来自 tag_mapping.USER_FATIGUE_MAX（50–180），换算到锚点侧约 5–18，
与 estimated_load（约 1.5–20）同量纲，使 100 分制对用户有区分度。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from anchor.slots import Slots
from anchor.tag_mapping import has_low_stamina_tag, has_profile_tag, resolve_fatigue_max

# 锚点关键词 → 体能系数（1–10，越高越累）
ANCHOR_DIFFICULTY_KEYWORDS: list[tuple[str, float]] = [
    ("登山", 8.5),
    ("爬山", 8.5),
    ("徒步", 7.5),
    ("长城", 8.0),
    ("紫金山", 7.0),
    ("中山陵", 5.5),  # 含台阶步行
    ("夫子庙", 3.5),
    ("博物馆", 2.0),
    ("博物院", 2.0),
    ("酒店", 1.5),
    ("度假", 1.5),
    ("美食", 2.0),
    ("演唱会", 3.0),
    ("赛事", 3.5),
    ("马拉松", 6.0),
]

DEFAULT_ANCHOR_DIFFICULTY = 4.0

ANCHOR_CATEGORY_DIFFICULTY: dict[str, float] = {
    "吃": 2.0,
    "住": 1.5,
    "玩": 6.5,
}

# 标签 → 对体能上限的修正（负值 = 更敏感、上限更低）
TAG_CAPACITY_DELTA: dict[str, float] = {
    "特种兵": 25,
    "行程节奏紧凑": 5,
    "景点打卡": 0,
    "酒店度假": -5,
    "行程节奏宽松": -5,
    "控制劳累度": -18,
    "带长辈": -22,
    "亲子游": -10,
    "长辈出行": -20,
    "轻度打卡": -8,
    "美食寻味": 0,
    "周末出行": -3,
    "短途": -2,
    "固定时间": -5,
}

# 标签 → 对预估劳累度的加成
TAG_LOAD_DELTA: dict[str, float] = {
    "特种兵": -3,
    "行程节奏紧凑": 4,
    "控制劳累度": 0,
    "带长辈": 2,
}

PACE_LOAD_FACTOR: dict[str, float] = {
    "normal": 1.0,
    "relaxed": 0.72,
    "compact": 1.12,
}

# POI 日疲劳上限 → 对话侧锚点可承受 load 的换算（USER_FATIGUE_MAX 50–180 → 5–18）
POI_TO_ANCHOR_CAPACITY_SCALE = 10.0
BASE_POI_CAPACITY = 55.0
MIN_ANCHOR_CAPACITY = 2.5
DAYS_DECAY_RATE = 0.12


def poi_capacity_to_anchor(poi_max: float) -> float:
    """将 POI/画像侧 F_max 换算为对话侧锚点体能上限。"""
    return poi_max / POI_TO_ANCHOR_CAPACITY_SCALE


@dataclass
class FatigueResult:
    estimated_load: float
    user_capacity: float
    has_conflict: bool
    anchor_difficulty: float
    days_factor: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "estimated_load": round(self.estimated_load, 2),
            "user_capacity": round(self.user_capacity, 2),
            "has_conflict": self.has_conflict,
            "anchor_difficulty": self.anchor_difficulty,
            "days_factor": round(self.days_factor, 2),
            "reason": self.reason,
            "fatigue_score": fatigue_display_score(self),
        }


def fatigue_display_score(fatigue: FatigueResult) -> int:
    """用户可见疲劳度 0–100，越高越累。"""
    if fatigue.user_capacity <= 0:
        return 100
    ratio = fatigue.estimated_load / fatigue.user_capacity
    return max(1, min(99, round(ratio * 100)))


def format_fatigue_brief(fatigue: FatigueResult, *, slots: Slots | None = None) -> str:
    score = fatigue_display_score(fatigue)
    line = f"预估疲劳度 {score} 分（100 分制，越低越轻松）"
    if slots and has_low_stamina_tag(slots.tags):
        line += "；已按带老人/小孩出行的节奏收紧强度"
    elif fatigue.has_conflict:
        line += "；当前略偏累，生成方案时我会帮你控节奏"
    return line


def _anchor_difficulty(anchor: str) -> float:
    text = anchor.strip()
    if text in ANCHOR_CATEGORY_DIFFICULTY:
        return ANCHOR_CATEGORY_DIFFICULTY[text]
    for keyword, score in ANCHOR_DIFFICULTY_KEYWORDS:
        if keyword in text:
            return score
    return DEFAULT_ANCHOR_DIFFICULTY


def _days_factor(days: int) -> float:
    return 1.0 + max(days - 1, 0) * DAYS_DECAY_RATE


def _user_capacity(tags: list[str]) -> float:
    if has_profile_tag(tags):
        return poi_capacity_to_anchor(resolve_fatigue_max(tags))
    poi_capacity = BASE_POI_CAPACITY
    for tag in tags:
        poi_capacity += TAG_CAPACITY_DELTA.get(tag, 0)
    return max(poi_capacity_to_anchor(poi_capacity), MIN_ANCHOR_CAPACITY)


def _rhythm_load_bonus(tags: list[str]) -> float:
    return sum(TAG_LOAD_DELTA.get(tag, 0) for tag in tags)


def evaluate_fatigue(
    slots: Slots,
    *,
    pace_modifier: str = "normal",
) -> FatigueResult:
    if not slots.is_complete_for_fatigue():
        raise ValueError("槽位未填满，无法计算劳累度")

    days = slots.days or 1
    anchor_diff = _anchor_difficulty(slots.anchor or "")
    days_factor = _days_factor(days)
    load_bonus = _rhythm_load_bonus(slots.tags)
    capacity = _user_capacity(slots.tags)

    load_factor = PACE_LOAD_FACTOR.get(pace_modifier, 1.0)
    estimated_load = (anchor_diff * days_factor + load_bonus) * load_factor

    tag_set = set(slots.tags)
    elderly_or_low_stamina = has_low_stamina_tag(slots.tags)
    high_effort_anchor = anchor_diff >= 6.0
    climb_anchor = slots.anchor == "玩" and anchor_diff >= 6.0

    # 语义冲突：低体力标签 + 高体能锚点（典型：带长辈爬山）
    if elderly_or_low_stamina and (high_effort_anchor or climb_anchor):
        sensitive = [
            t
            for t in slots.tags
            if t in tag_set and has_low_stamina_tag([t])
        ]
        reason = (
            f"锚点「{slots.anchor}」对体力要求较高（系数 {anchor_diff}），"
            f"与标签 {sensitive} 存在明显冲突"
        )
        return FatigueResult(
            estimated_load=estimated_load,
            user_capacity=capacity,
            has_conflict=True,
            anchor_difficulty=anchor_diff,
            days_factor=days_factor,
            reason=reason,
        )

    has_conflict = estimated_load > capacity

    if has_conflict:
        sensitive = [t for t in slots.tags if has_low_stamina_tag([t])]
        score = fatigue_display_score(
            FatigueResult(
                estimated_load=estimated_load,
                user_capacity=capacity,
                has_conflict=True,
                anchor_difficulty=anchor_diff,
                days_factor=days_factor,
                reason="",
            )
        )
        if sensitive and anchor_diff >= 6:
            reason = (
                f"锚点「{slots.anchor}」体能系数 {anchor_diff} 偏高，"
                f"与标签 {sensitive} 不匹配（预估疲劳约 {score} 分）"
            )
        else:
            reason = (
                f"预估疲劳约 {score} 分，超出当前画像可承受强度 "
                f"（{days} 天 × 锚点系数 {anchor_diff}）"
            )
    else:
        reason = "体能预估在可接受范围内"

    return FatigueResult(
        estimated_load=estimated_load,
        user_capacity=capacity,
        has_conflict=has_conflict,
        anchor_difficulty=anchor_diff,
        days_factor=days_factor,
        reason=reason,
    )
