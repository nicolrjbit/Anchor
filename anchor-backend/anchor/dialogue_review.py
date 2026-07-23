"""Agent 回复内容审核：避免重复追问已回答/已采集的槽位。"""

from __future__ import annotations

import re
from typing import Any, Callable

from anchor.nlu import (
    apply_mode_profile_default,
    apply_uncertain_days_default,
    finalize_slots,
)
from anchor.prompts import pick_focus
from anchor.slots import Slots
from anchor.state_machine import Session
from anchor.tag_mapping import has_profile_tag
from anchor.transport_mapping import transport_is_satisfied

FOCUS_QUESTION_MARKERS: dict[str, tuple[str, ...]] = {
    "destination": ("去哪", "哪个城市", "哪座城市", "目的地", "打算去"),
    "days": ("几天", "多少天", "天数", "玩几天"),
    "anchor": ("想吃", "想住", "想逛", "主要是吃", "主要是住", "主要是玩"),
    "tags": ("和谁一起", "同行", "什么人", "带娃", "陪爸妈", "一个人"),
    "transport": ("地铁", "步行", "自驾", "租车", "路上希望", "出行方式"),
}

FOLLOWUP_ALTERNATES: dict[str, str] = {
    "destination": "你想先选哪座城市？北京、南京、重庆、新疆、成都、西安都可以～",
    "days": "这趟大概安排几天？直接说数字就行～",
    "anchor": "这趟你更想以吃、住还是逛为主？说个大方向就好～",
    "tags": "再确认下：是一个人、和朋友，还是带娃/陪长辈？随便说个最接近的～",
    "transport": "路上你更倾向地铁加步行，还是自驾/租车呀？",
}


def slot_filled_this_turn(focus: str, before: Slots, after: Slots) -> bool:
    if focus == "destination":
        return bool(after.destination) and after.destination != before.destination
    if focus == "days":
        return after.days is not None and after.days != before.days
    if focus == "anchor":
        return bool(after.anchor) and after.anchor != before.anchor
    if focus == "tags":
        return has_profile_tag(after.tags) and not has_profile_tag(before.tags)
    if focus == "transport":
        return transport_is_satisfied(after.transport_preferences) and not transport_is_satisfied(
            before.transport_preferences
        )
    return False


def _slot_is_satisfied(focus: str, slots: Slots, *, mode: str | None) -> bool:
    return focus not in slots.missing(mode=mode)


def reinfer_slots_from_message(message: str, slots: Slots, *, mode: str | None) -> Slots:
    """对用户最新回复再推断一次，减少「答了但没提取到」导致的重复追问。"""
    updated = finalize_slots(message, slots, mode=mode)
    updated, _ = apply_uncertain_days_default(message, updated, mode=mode)
    updated = apply_mode_profile_default(message, updated, mode=mode)
    return updated


def resolve_followup_focus(
    missing: list[str],
    *,
    mode: str | None,
    before: Slots,
    after: Slots,
    last_asked_focus: str | None,
    message: str,
) -> tuple[str, list[str], Slots]:
    """选择本轮追问焦点；若上一轮已问过且用户本轮未补齐，尝试再推断或换问下一项。"""
    slots = after
    missing = list(slots.missing(mode=mode))
    if not missing:
        return last_asked_focus or "destination", missing, slots

    focus = pick_focus(missing, mode=mode)
    if slot_filled_this_turn(focus, before, slots):
        missing = list(slots.missing(mode=mode))
        if not missing:
            return focus, missing, slots
        focus = pick_focus(missing, mode=mode)

    if last_asked_focus == focus and focus in missing:
        slots = reinfer_slots_from_message(message, slots, mode=mode)
        missing = list(slots.missing(mode=mode))
        if focus not in missing:
            if missing:
                focus = pick_focus(missing, mode=mode)
            return focus, missing, slots

        others = [item for item in missing if item != focus]
        if others:
            focus = pick_focus(others, mode=mode)

    return focus, missing, slots


def detect_repeat_question(
    reply: str,
    focus: str,
    *,
    last_asked_focus: str | None,
    last_reply: str | None,
) -> bool:
    if not last_reply or not reply.strip():
        return False
    normalized_new = re.sub(r"\s+", "", reply.strip())
    normalized_old = re.sub(r"\s+", "", last_reply.strip())
    if normalized_new == normalized_old:
        return True
    if last_asked_focus != focus:
        return False
    markers = FOCUS_QUESTION_MARKERS.get(focus, ())
    if not markers:
        return False
    new_hits = sum(1 for marker in markers if marker in reply)
    old_hits = sum(1 for marker in markers if marker in last_reply)
    return new_hits > 0 and old_hits > 0


def rephrase_followup(focus: str, slots: Slots, *, mode: str | None) -> str:
    alternate = FOLLOWUP_ALTERNATES.get(focus)
    if alternate:
        return alternate
    from anchor.prompts import FALLBACK_QUESTIONS, build_profile_tag_followup, build_transport_followup

    if focus == "tags":
        return build_profile_tag_followup(slots)
    if focus == "transport":
        return build_transport_followup(slots)
    return FALLBACK_QUESTIONS.get(focus, "还有什么想补充的吗？")


def review_slot_followup(
    *,
    session: Session,
    missing: list[str],
    before: Slots,
    after: Slots,
    message: str,
    mode: str | None,
    extra_note: str | None,
    build_question: Callable[[str, Slots], str],
    build_ack: Callable[[Slots, Slots], str],
    compose: Callable[..., str],
) -> tuple[str, str, list[str], Slots, dict[str, Any]]:
    """审核并生成 slot 追问回复，返回 (reply, focus, missing, slots, audit_meta)。"""
    focus, missing, slots = resolve_followup_focus(
        missing,
        mode=mode,
        before=before,
        after=after,
        last_asked_focus=session.last_asked_focus,
        message=message,
    )
    audit: dict[str, Any] = {"reviewed": True}

    if not missing:
        audit["action"] = "no_missing_after_review"
        return "", focus, missing, slots, audit

    question = build_question(focus, slots)
    ack = build_ack(before, slots)
    reply = compose(ack, question, extra_note=extra_note)

    if detect_repeat_question(
        reply,
        focus,
        last_asked_focus=session.last_asked_focus,
        last_reply=session.last_assistant_reply,
    ):
        audit["repeat_detected"] = True
        question = rephrase_followup(focus, slots, mode=mode)
        reply = compose(ack, question, extra_note=extra_note)
        audit["rephrased"] = True

    if _slot_is_satisfied(focus, slots, mode=mode):
        audit["focus_already_satisfied"] = True
        remaining = list(slots.missing(mode=mode))
        if remaining:
            focus = pick_focus(remaining, mode=mode)
            question = build_question(focus, slots)
            reply = compose(build_ack(before, slots), question, extra_note=extra_note)
            missing = remaining

    audit["focus"] = focus
    return reply, focus, missing, slots, audit
