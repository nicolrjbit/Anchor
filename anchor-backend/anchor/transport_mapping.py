"""出行方式偏好解析（P2 对话采集 → 路段推荐）。"""

from __future__ import annotations

import re
from typing import Any

VALID_TRANSPORT_MODES = frozenset({"公交", "地铁", "骑行", "步行", "自驾"})
DEFAULT_TRANSPORT = ["地铁", "步行"]

FLEXIBLE_TRANSPORT_RE = re.compile(
    r"都可以|随便|看情况|你定|都行|不太挑|无所谓|怎么方便|你看着"
)


def normalize_transport_preferences(prefs: list[str] | None) -> list[str]:
    if not prefs:
        return []
    out: list[str] = []
    for raw in prefs:
        mode = "自驾" if raw == "汽车" else str(raw).strip()
        if mode in VALID_TRANSPORT_MODES and mode not in out:
            out.append(mode)
    return out


def transport_is_satisfied(prefs: list[str] | None) -> bool:
    return bool(normalize_transport_preferences(prefs))


def extract_transport_preferences(text: str) -> list[str] | None:
    t = text.strip()
    if not t:
        return None
    if FLEXIBLE_TRANSPORT_RE.search(t):
        return list(DEFAULT_TRANSPORT)
    if re.search(r"自驾|租车|开车|自己开|有车|开自己的", t):
        return ["自驾"]
    if re.search(r"地铁步行|地铁\+步行", t):
        return ["地铁", "步行"]
    if re.search(r"地铁.*步行|步行.*地铁|轨交|轨道交通", t):
        return ["地铁", "步行"]
    if re.search(r"地铁", t) and re.search(r"步行|走路", t):
        return ["地铁", "步行"]
    if re.search(r"公交.*地铁|地铁.*公交", t):
        return ["公交", "地铁"]
    if re.search(r"只坐地铁|地铁为主|坐地铁|乘地铁", t):
        return ["地铁"]
    if re.search(r"公交|巴士", t):
        return ["公交"]
    if re.search(r"骑行|骑车|单车|共享单车", t):
        return ["骑行"]
    if re.search(r"步行|走路|多走|溜达", t):
        return ["步行"]
    found = [m for m in ("地铁", "公交", "骑行", "步行", "自驾") if m in t]
    if found:
        return normalize_transport_preferences(found)
    return None


def describe_transport_preferences(prefs: list[str] | None) -> str:
    normalized = normalize_transport_preferences(prefs)
    if not normalized:
        return ""
    if normalized == ["自驾"]:
        return "自驾/租车"
    if set(normalized) >= {"地铁", "步行"}:
        return "地铁加步行"
    return "、".join(normalized)


def resolve_session_transport_preferences(session: dict[str, Any]) -> list[str]:
    """从 session 或 slots 读取 P2 采集的出行偏好。"""
    prefs = normalize_transport_preferences(session.get("transport_preferences"))
    if prefs:
        return prefs
    slots = session.get("slots") or {}
    return normalize_transport_preferences(slots.get("transport_preferences"))
