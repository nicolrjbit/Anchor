"""多轮对话主处理器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anchor.fatigue import (
    evaluate_fatigue,
    fatigue_display_score,
)
from anchor.modifications import (
    apply_modification_hints,
    care_note_for_tags,
    describe_plan_adjustment,
    infer_pace_modifier,
    is_modification_intent,
)
from anchor.dialogue_review import review_slot_followup
from anchor.nlu import LLMClient, apply_mode_profile_default, apply_uncertain_days_default, extract_slots
from anchor.prompts import (
    ALREADY_CONVERGED_REPLY,
    FALLBACK_QUESTIONS,
    build_convergence_message,
    build_modification_reply,
    build_multi_slot_ack,
    build_profile_tag_followup,
    build_slot_progress,
    build_transport_followup,
    build_unsupported_destination_reply,
    compose_followup,
    pick_focus,
)
from anchor.transport_mapping import normalize_transport_preferences
from anchor.anchor_recommendations import build_anchor_recommendations
from anchor.slots import Slots, destination_is_supported
from anchor.state_machine import Session, StateMachine
from anchor.states import State


@dataclass
class DialogueTurn:
    """单次对话返回。"""

    reply: str
    session: Session
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "session": self.session.to_dict(),
            "meta": self.meta,
        }


_ANCHOR_PICK_LIMIT = 8  # 锚点页展示的候选数（POI 库已扩，给用户更多可选）


def _snapshot_slots(slots: Slots) -> Slots:
    return Slots(
        destination=slots.destination,
        days=slots.days,
        anchor=slots.anchor,
        tags=list(slots.tags),
        transport_preferences=list(slots.transport_preferences),
    )


def _sync_transport_to_session(session: Session) -> None:
    prefs = normalize_transport_preferences(session.slots.transport_preferences)
    if prefs:
        session.transport_preferences = prefs


def _missing_slot_question(missing: list[str], slots: Slots, *, mode: str | None) -> str:
    """无 LLM 时的模板追问（一次只问一项）。"""
    focus = pick_focus(missing, mode=mode)
    if focus == "tags":
        return build_profile_tag_followup(slots)
    if focus == "transport":
        return build_transport_followup(slots)
    return FALLBACK_QUESTIONS[focus]


def _generate_slot_followup(
    session: Session,
    missing: list[str],
    slots: Slots,
    llm: LLMClient | None,
    latest_message: str,
    *,
    mode: str | None,
    before: Slots,
    extra_note: str | None = None,
) -> tuple[str, list[str], Slots, dict[str, Any]]:
    def build_question(focus: str, current: Slots) -> str:
        if focus == "transport":
            return build_transport_followup(current, extra_note=extra_note)
        return _missing_slot_question([focus], current, mode=mode)

    reply, focus, missing, slots, audit = review_slot_followup(
        session=session,
        missing=missing,
        before=before,
        after=slots,
        message=latest_message,
        mode=mode,
        extra_note=extra_note,
        build_question=build_question,
        build_ack=build_multi_slot_ack,
        compose=compose_followup,
    )
    session.last_asked_focus = focus
    session.last_assistant_reply = reply
    return reply, missing, slots, audit


def _unsupported_destination(slots: Slots) -> str | None:
    dest = slots.destination
    if dest and not destination_is_supported(dest):
        return dest
    return None


def _apply_anchor_recommendations(session: Session) -> None:
    """写入 session 供 P3 使用；收束文案不再展示 POI 详情。"""
    bundle = build_anchor_recommendations(session.slots, limit=_ANCHOR_PICK_LIMIT)
    if bundle:
        session.anchor_recommendations = [p.to_dict() for p in bundle.picks]
    else:
        session.anchor_recommendations = None


def _enrich_meta(meta: dict[str, Any], slots: Slots, *, mode: str | None) -> None:
    meta["slot_progress"] = build_slot_progress(slots, mode=mode)


def _prev_fatigue_score(session: Session) -> int | None:
    detail = session.conflict_detail or {}
    if "fatigue_score" in detail:
        return int(detail["fatigue_score"])
    return None


def _apply_fatigue(session: Session) -> tuple[Any, int]:
    fatigue = evaluate_fatigue(
        session.slots,
        pace_modifier=session.pace_modifier,
    )
    session.has_conflict = fatigue.has_conflict
    session.conflict_detail = fatigue.to_dict()
    return fatigue, fatigue_display_score(fatigue)


def _build_first_convergence_reply(session: Session, fatigue: Any, score: int) -> str:
    _sync_transport_to_session(session)
    _apply_anchor_recommendations(session)
    care = care_note_for_tags(session.slots.tags)
    return build_convergence_message(
        session.slots,
        care_note=care,
    )


def _process_slot_extraction(
    session: Session,
    message: str,
    llm: LLMClient | None,
    mode: str | None,
) -> tuple[Slots, str | None, str | None]:
    """NLU 合并槽位，处理天数默认；返回 (before, days_note, unsupported_city)。"""
    before = _snapshot_slots(session.slots)
    session.slots = extract_slots(message, session.slots, llm, mode=mode)
    session.slots, days_note = apply_uncertain_days_default(
        message, session.slots, mode=mode
    )
    session.slots = apply_mode_profile_default(message, session.slots, mode=mode)
    unsupported = _unsupported_destination(session.slots)
    return before, days_note, unsupported


def _handle_convergence_turn(
    session: Session,
    message: str,
    llm: LLMClient | None,
    mode: str | None,
    meta: dict[str, Any],
) -> DialogueTurn:
    prev_score = _prev_fatigue_score(session)
    text = message.strip()

    if not is_modification_intent(text):
        _enrich_meta(meta, session.slots, mode=mode)
        return DialogueTurn(
            reply=ALREADY_CONVERGED_REPLY,
            session=session,
            meta={**meta, "action": "already_converged"},
        )

    before, days_note, unsupported = _process_slot_extraction(
        session, message, llm, mode
    )
    session.slots = apply_modification_hints(message, session.slots)
    session.pace_modifier = infer_pace_modifier(message, session.pace_modifier)

    if unsupported:
        session.current_state = State.SLOT_FILLING
        reply = build_unsupported_destination_reply(unsupported)
        _enrich_meta(meta, session.slots, mode=mode)
        return DialogueTurn(
            reply=reply,
            session=session,
            meta={
                **meta,
                "action": "unsupported_destination",
                "missing": ["destination"],
            },
        )

    missing = session.slots.missing(mode=mode)
    if missing:
        session.current_state = State.SLOT_FILLING
        reply, missing, session.slots, review_meta = _generate_slot_followup(
            session,
            missing,
            session.slots,
            llm,
            message,
            mode=mode,
            before=before,
            extra_note=days_note,
        )
        _enrich_meta(meta, session.slots, mode=mode)
        return DialogueTurn(
            reply=reply,
            session=session,
            meta={**meta, "action": "slot_followup", "missing": missing, "review": review_meta},
        )

    fatigue, new_score = _apply_fatigue(session)
    session.current_state = State.CONVERGENCE
    care = care_note_for_tags(session.slots.tags)
    pace_label = describe_plan_adjustment(session.pace_modifier)
    _apply_anchor_recommendations(session)
    _sync_transport_to_session(session)

    if prev_score is not None:
        reply = build_modification_reply(
            session.slots,
            prev_score=prev_score,
            new_score=new_score,
            care_note=care,
            pace_label=pace_label,
        )
        action = "modify"
    else:
        reply = _build_first_convergence_reply(session, fatigue, new_score)
        action = "converge"

    meta["fatigue"] = session.conflict_detail
    meta["fatigue_delta"] = (
        {"from": prev_score, "to": new_score} if prev_score is not None else None
    )
    _enrich_meta(meta, session.slots, mode=mode)
    return DialogueTurn(
        reply=reply,
        session=session,
        meta={**meta, "action": action},
    )


def handle_user_message(
    session: Session,
    message: str,
    llm: LLMClient | None = None,
    *,
    mode: str | None = None,
) -> DialogueTurn:
    """
    用户消息入口。

    流程：
    1. INIT → 首条消息进入 SLOT_FILLING
    2. SLOT_FILLING → NLU 提取 → 缺槽位则 bounded 追问
    3. 槽满 → 劳累度预计算 → CONVERGENCE（含量化疲劳度）
    4. CONVERGENCE → 支持修改意图并对比疲劳度变化
    """
    meta: dict[str, Any] = {"previous_state": session.current_state.value}

    if session.current_state == State.RISK_CLARIFY:
        session.current_state = State.CONVERGENCE
        meta["transition"] = "RISK_CLARIFY → CONVERGENCE"

    if session.current_state == State.CONVERGENCE:
        return _handle_convergence_turn(session, message, llm, mode, meta)

    if session.current_state == State.INIT:
        session.current_state = StateMachine.on_init_user_message()
        meta["transition"] = "INIT → SLOT_FILLING"

    before, days_note, unsupported = _process_slot_extraction(
        session, message, llm, mode
    )
    meta["slots_after_nlu"] = session.slots.to_dict()

    if unsupported:
        session.current_state = State.SLOT_FILLING
        reply = build_unsupported_destination_reply(unsupported)
        _enrich_meta(meta, session.slots, mode=mode)
        return DialogueTurn(
            reply=reply,
            session=session,
            meta={
                **meta,
                "action": "unsupported_destination",
                "missing": ["destination"],
            },
        )

    missing = session.slots.missing(mode=mode)
    if missing:
        session.current_state = State.SLOT_FILLING
        reply, missing, session.slots, review_meta = _generate_slot_followup(
            session,
            missing,
            session.slots,
            llm,
            message,
            mode=mode,
            before=before,
            extra_note=days_note,
        )
        _enrich_meta(meta, session.slots, mode=mode)
        return DialogueTurn(
            reply=reply,
            session=session,
            meta={**meta, "action": "slot_followup", "missing": missing, "review": review_meta},
        )

    fatigue, score = _apply_fatigue(session)
    if session.baseline_fatigue_score is None:
        session.baseline_fatigue_score = score
    session.current_state = StateMachine.on_check_data(
        session.slots,
        session.has_conflict,
    )
    reply = _build_first_convergence_reply(session, fatigue, score)
    meta["fatigue"] = session.conflict_detail
    _enrich_meta(meta, session.slots, mode=mode)
    return DialogueTurn(
        reply=reply,
        session=session,
        meta={**meta, "action": "converge"},
    )
