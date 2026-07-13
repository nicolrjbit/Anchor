"""NLU 槽位提取 — LLM 接口 + 规则兜底（测试/无 API 时）。"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from anchor.prompts import NLU_SYSTEM_PROMPT, NLU_USER_TEMPLATE
from anchor.slots import (
    Slots,
    anchor_is_satisfied,
    infer_anchor_category,
    normalize_anchor,
    normalize_destination,
)
from anchor.tag_mapping import extract_profile_tags, has_profile_tag, resolve_profile_tags
from anchor.transport_mapping import extract_transport_preferences

LANDMARK_PATTERN = re.compile(
    r"(新街口|解放碑|王府井|春熙路|外滩|西湖|故宫|兵马俑|洪崖洞|夫子庙|"
    r"紫金山|中山陵|长城|迪士尼|大巴扎|观音桥)"
)

FOOD_CATEGORY_PATTERN = re.compile(
    r"(火锅|小面|板鸭|烤鸭|烧烤|串串|江湖菜|小吃|早茶|烤羊肉串|美食)"
)

VAGUE_ACK_PATTERN = re.compile(r"^(有|对|嗯|是|好|可以|行|没错|是的)[。！]?$")
UNCERTAIN_DAYS_PATTERN = re.compile(
    r"不确定|看情况|随便|都行|没想好|再说|灵活|Flexible|看心情"
)
DEFAULT_DAYS_BY_MODE: dict[str, int] = {
    "ROUTE": 3,
    "FOOD": 3,
    "FILL": 2,
    "EVENT": 1,
    "RISK": 3,
}
DEFAULT_DAYS_FALLBACK = 3

# P1 模式默认用户画像（EVENT 自动带上，其它模式在用户说「随便」时兜底）
DEFAULT_PROFILE_BY_MODE: dict[str, str] = {
    "EVENT": "商务出差",
    "ROUTE": "年轻情侣/朋友",
    "FOOD": "年轻情侣/朋友",
    "FILL": "上班族",
    "BUDGET": "年轻情侣/朋友",
}
PROFILE_VAGUE_ACK_PATTERN = re.compile(
    r"^(随便|都行|都可以|不知道|没想好|普通|一般|没啥|无所谓|看你|你定|看着办)[。！]?$"
)
BARE_DAYS_PATTERN = re.compile(r"^(\d{1,2})$")
BARE_CN_DAYS_PATTERN = re.compile(r"^([一二三四五六七八九十两]+)$")


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def apply_uncertain_days_default(
    message: str,
    slots: Slots,
    *,
    mode: str | None = None,
) -> tuple[Slots, str | None]:
    """用户表示天数不确定时，按模式给默认天数并返回说明文案。"""
    if slots.days is not None and slots.days > 0:
        return slots, None
    if not UNCERTAIN_DAYS_PATTERN.search(message.strip()):
        return slots, None
    default = DEFAULT_DAYS_BY_MODE.get(mode or "", DEFAULT_DAYS_FALLBACK)
    updated = slots.merge({"days": default}, mode=mode)
    note = f"天数你先不定的话，我先按 {default} 天排，后面还能改"
    return updated, note


def apply_mode_profile_default(
    message: str,
    slots: Slots,
    *,
    mode: str | None = None,
) -> Slots:
    """EVENT 等模式自动补用户画像；用户说「随便」时按模式给合理默认。"""
    if has_profile_tag(slots.tags):
        return slots
    default = DEFAULT_PROFILE_BY_MODE.get(mode or "")
    if not default:
        return slots
    if mode == "EVENT" or PROFILE_VAGUE_ACK_PATTERN.match(message.strip()):
        return slots.merge({"tags": [default]}, mode=mode)
    return slots


def infer_days(text: str, current: Slots) -> int | None:
    """单独数字/中文数也视为天数（回答「玩几天」的语境）。"""
    if current.days is not None:
        return None
    stripped = text.strip()
    m = RuleBasedNLU.DAYS_PATTERN.search(stripped)
    if m:
        if m.group(1):
            return int(m.group(1))
        if m.group(2):
            return RuleBasedNLU.CN_NUM.get(m.group(2))
    m = BARE_DAYS_PATTERN.match(stripped)
    if m:
        days = int(m.group(1))
        if 1 <= days <= 30:
            return days
    m = BARE_CN_DAYS_PATTERN.match(stripped)
    if m:
        return RuleBasedNLU.CN_NUM.get(m.group(1))
    return None


def freeze_mode_anchor(mode: str | None, before: Slots, after: Slots) -> Slots:
    """P1 模式 + 锚点大类已定后，不被后续闲聊改写成别的类型。"""
    if not mode or not anchor_is_satisfied(before.anchor):
        return after
    if mode in ("ROUTE", "EVENT", "FOOD", "FILL"):
        return Slots(
            destination=after.destination,
            days=after.days,
            anchor=before.anchor,
            tags=after.tags,
            transport_preferences=list(after.transport_preferences),
        )
    return after


class RuleBasedNLU:
    """无 LLM 时的规则提取，便于单测与本地调试。"""

    CITY_PATTERN = re.compile(
        r"(南京|上海|成都|北京|杭州|西安|重庆|广州|深圳|苏州|武汉|厦门|青岛|大连|长沙|昆明|新疆)"
    )
    DAYS_PATTERN = re.compile(r"(\d+)\s*天|([一二三四五六七八九十两]+)\s*天")

    CN_NUM = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def extract(self, message: str, current: Slots) -> dict[str, Any]:
        text = message.strip()
        patch: dict[str, Any] = {}

        m_city = self.CITY_PATTERN.search(text)
        if m_city:
            patch["destination"] = normalize_destination(m_city.group(1))

        m_days = self.DAYS_PATTERN.search(text)
        if m_days:
            if m_days.group(1):
                patch["days"] = int(m_days.group(1))
            elif m_days.group(2):
                cn = m_days.group(2)
                patch["days"] = self.CN_NUM.get(cn, None)

        inferred_days = infer_days(text, current)
        if inferred_days is not None:
            patch["days"] = inferred_days

        profile_tags = extract_profile_tags(text)
        if profile_tags:
            patch["tags"] = profile_tags

        anchor = infer_anchor_category(text=text)
        if anchor:
            patch["anchor"] = anchor

        transport = extract_transport_preferences(text)
        if transport:
            patch["transport_preferences"] = transport

        return patch


MODE_DEFAULT_TAGS: dict[str, list[str]] = {}


def default_anchor_for_mode(mode: str) -> str | None:
    return infer_anchor_category(mode=mode)


def apply_mode_defaults(mode: str | None, slots: Slots) -> Slots:
    """文本未抽出锚点时，用 P1 模式补全 吃 / 住 / 玩。"""
    if not mode or anchor_is_satisfied(slots.anchor):
        return slots

    default = default_anchor_for_mode(mode)
    if not default:
        return slots
    return slots.merge({"anchor": default}, mode=mode)


def apply_mode_hints(mode: str | None, message: str, slots: Slots) -> Slots:
    """结合 P1 模式，从首条文案补全锚点大类。"""
    if not mode or anchor_is_satisfied(slots.anchor):
        return slots

    anchor = infer_anchor_category(text=message.strip(), mode=mode)
    if anchor:
        return slots.merge({"anchor": anchor}, mode=mode)
    return slots


def finalize_slots(message: str, slots: Slots, *, mode: str | None = None) -> Slots:
    text = message.strip()

    if VAGUE_ACK_PATTERN.match(text) and slots.anchor:
        return slots

    inferred_days = infer_days(text, slots)
    if inferred_days is not None:
        slots = slots.merge({"days": inferred_days}, mode=mode)

    if not anchor_is_satisfied(slots.anchor):
        anchor = infer_anchor_category(text=text, mode=mode)
        if anchor:
            slots = slots.merge({"anchor": anchor}, mode=mode)

    profile_tags = extract_profile_tags(text)
    if profile_tags:
        slots = slots.merge({"tags": profile_tags}, mode=mode)

    transport = extract_transport_preferences(text)
    if transport:
        slots = slots.merge({"transport_preferences": transport}, mode=mode)

    return slots


def _parse_nlu_json(raw: str, *, mode: str | None = None, text: str = "") -> dict[str, Any]:
    payload = raw.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*", "", payload)
        payload = re.sub(r"\s*```$", "", payload)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}

    out: dict[str, Any] = {}
    if data.get("destination"):
        out["destination"] = normalize_destination(str(data["destination"]).strip())
    if data.get("days") is not None:
        try:
            out["days"] = int(data["days"])
        except (TypeError, ValueError):
            pass
    if data.get("anchor"):
        anchor = normalize_anchor(str(data["anchor"]).strip(), mode=mode, text=text)
        if anchor:
            out["anchor"] = anchor
    tags = data.get("tags")
    if tags:
        if isinstance(tags, str):
            tags = [tags]
        raw_tags = [str(t).strip() for t in tags if str(t).strip()]
        resolved = resolve_profile_tags(raw_tags)
        if resolved:
            out["tags"] = resolved
    transport = data.get("transport_preferences")
    if transport:
        if isinstance(transport, str):
            transport = [transport]
        if isinstance(transport, list):
            out["transport_preferences"] = [str(t).strip() for t in transport if str(t).strip()]
    return out


def extract_slots(
    message: str,
    current: Slots,
    llm: LLMClient | None = None,
    *,
    use_rules_fallback: bool = True,
    mode: str | None = None,
) -> Slots:
    """LLM 提取 + 与当前槽位合并；LLM 失败时可规则兜底。"""
    patch: dict[str, Any] = {}

    if llm is not None:
        user = NLU_USER_TEMPLATE.format(
            current_slots=json.dumps(current.to_dict(), ensure_ascii=False),
            message=message,
        )
        raw = llm.complete(NLU_SYSTEM_PROMPT, user)
        patch = _parse_nlu_json(raw, mode=mode, text=message)

    if use_rules_fallback and not patch:
        patch = RuleBasedNLU().extract(message, current)

    if llm is not None and use_rules_fallback:
        rule_patch = RuleBasedNLU().extract(message, current)
        for key, val in rule_patch.items():
            if key == "tags":
                existing = patch.get("tags") or []
                merged = resolve_profile_tags(
                    [
                        *(existing if isinstance(existing, list) else []),
                        *(val if isinstance(val, list) else []),
                    ]
                )
                if merged:
                    patch["tags"] = merged
            elif key not in patch or not patch[key]:
                patch[key] = val

    if use_rules_fallback and not patch.get("tags"):
        profile_tags = extract_profile_tags(message)
        if profile_tags:
            patch["tags"] = profile_tags

    if use_rules_fallback and not patch.get("transport_preferences"):
        transport = extract_transport_preferences(message)
        if transport:
            patch["transport_preferences"] = transport

    merged = current.merge(patch, mode=mode)
    merged = apply_mode_hints(mode, message, merged)
    merged = finalize_slots(message, merged, mode=mode)
    merged = apply_mode_defaults(mode, merged)
    return freeze_mode_anchor(mode, current, merged)
