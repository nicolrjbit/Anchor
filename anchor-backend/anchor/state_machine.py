"""旅游 Agent 状态机 — 与用户提供的 StateMachineConfig 对齐。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anchor.slots import Slots
from anchor.states import State


@dataclass
class Session:
    current_state: State = State.INIT
    slots: Slots = field(default_factory=Slots)
    has_conflict: bool = False
    conflict_detail: dict[str, Any] | None = None
    risk_resolved: bool = False
    baseline_fatigue_score: int | None = None
    pace_modifier: str = "normal"
    anchor_recommendations: list[dict[str, Any]] | None = None
    selected_anchor_poi: dict[str, Any] | None = None
    selected_anchor_pois: list[dict[str, Any]] | None = None
    selected_follow_pois: list[dict[str, Any]] | None = None
    transport_preferences: list[str] | None = None
    p1_mode: str | None = None
    travel_mode: str | None = None
    transport_modes: dict[str, str] | None = None
    transport_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "slots": self.slots.to_dict(),
            "has_conflict": self.has_conflict,
            "conflict_detail": self.conflict_detail,
            "risk_resolved": self.risk_resolved,
            "baseline_fatigue_score": self.baseline_fatigue_score,
            "pace_modifier": self.pace_modifier,
            "anchor_recommendations": self.anchor_recommendations,
            "selected_anchor_poi": self.selected_anchor_poi,
            "selected_anchor_pois": self.selected_anchor_pois,
            "selected_follow_pois": self.selected_follow_pois,
            "transport_preferences": self.transport_preferences,
            "p1_mode": self.p1_mode,
            "travel_mode": self.travel_mode,
            "transport_modes": self.transport_modes,
            "transport_confirmed": self.transport_confirmed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Session:
        if not data:
            return cls()
        slots_data = data.get("slots") or {}
        slots = Slots(
            destination=slots_data.get("destination"),
            days=slots_data.get("days"),
            anchor=slots_data.get("anchor"),
            tags=list(slots_data.get("tags") or []),
            transport_preferences=list(slots_data.get("transport_preferences") or []),
        )
        transport_preferences = list(data.get("transport_preferences") or [])
        if not transport_preferences and slots.transport_preferences:
            transport_preferences = list(slots.transport_preferences)
        state_value = data.get("current_state", State.INIT.value)
        return cls(
            current_state=State(state_value),
            slots=slots,
            has_conflict=bool(data.get("has_conflict", False)),
            conflict_detail=data.get("conflict_detail"),
            risk_resolved=bool(data.get("risk_resolved", False)),
            baseline_fatigue_score=data.get("baseline_fatigue_score"),
            pace_modifier=str(data.get("pace_modifier") or "normal"),
            anchor_recommendations=list(data.get("anchor_recommendations") or []) or None,
            selected_anchor_poi=data.get("selected_anchor_poi"),
            selected_anchor_pois=list(data.get("selected_anchor_pois") or []) or None,
            selected_follow_pois=list(data.get("selected_follow_pois") or []) or None,
            transport_preferences=transport_preferences or None,
            p1_mode=data.get("p1_mode"),
            travel_mode=data.get("travel_mode"),
            transport_modes=dict(data.get("transport_modes") or {}) or None,
            transport_confirmed=bool(data.get("transport_confirmed", False)),
        )


class StateMachine:
    """状态转换：INIT → SLOT_FILLING → (RISK_CLARIFY?) → CONVERGENCE"""

    @staticmethod
    def on_init_user_message() -> State:
        return State.SLOT_FILLING

    @staticmethod
    def on_check_data(slots: Slots, has_conflict: bool) -> State:
        if not slots.is_complete():
            return State.SLOT_FILLING
        return State.CONVERGENCE

    @staticmethod
    def on_user_confirm() -> State:
        return State.CONVERGENCE
