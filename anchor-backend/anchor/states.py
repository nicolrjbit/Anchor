"""锚点 Anchor 平台 — 对话状态定义。"""

from enum import Enum


class State(str, Enum):
    INIT = "INIT"
    SLOT_FILLING = "SLOT_FILLING"
    RISK_CLARIFY = "RISK_CLARIFY"
    CONVERGENCE = "CONVERGENCE"


STATES = State

# 对话采集要素（destination / days / anchor / tags / transport）
REQUIRED_SLOTS = ("destination", "days", "anchor", "tags", "transport")
