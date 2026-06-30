"""行程专家建议生成 — 将诊断结果转为用户可读文案。"""

from __future__ import annotations

import json
from typing import Protocol

from anchor.plan_diagnosis import PlanDiagnosis, PlanMetrics, diagnose_plan
from anchor.prompts import PLAN_ADVISOR_SYSTEM, PLAN_ADVISOR_USER_TEMPLATE


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _tag_phrase(tags: list[str]) -> str:
    if not tags:
        return "您的出行偏好"
    return "、".join(tags)


def expand_with_template(diagnosis: PlanDiagnosis) -> str:
    """无 LLM 时：基于标准描述 + 标签做轻量口语化，不发明数值。"""
    lines: list[str] = []

    for item in diagnosis.pros:
        prefix = f"第{item.day_index}天" if item.day_index else "整体"
        if item.rule_key == "high_matching":
            lines.append(
                f"- 作为{_tag_phrase(diagnosis.tags)}，{prefix}行程{item.standard_text.replace('【高纯度量身定制】：', '')}"
            )
        elif item.rule_key == "hardcore_full":
            lines.append(
                f"- 看得出您是{_tag_phrase(diagnosis.tags)}的玩法，{item.standard_text.replace('【硬核充实，值回票价】：', '')}"
            )
        else:
            text = item.standard_text.split("】：", 1)[-1]
            lines.append(f"- {text}")

    for item in diagnosis.cons:
        text = item.standard_text.split("】：", 1)[-1]
        tip = item.preset_tip or ""
        day_hint = f"（第{item.day_index}天）" if item.day_index else ""
        lines.append(f"- {day_hint}{text}{(' ' + tip) if tip else ''}")

    if not lines:
        lines.append(
            f"- 已为{diagnosis.destination}{diagnosis.days}天行程围绕「{diagnosis.anchor}」做好安排，"
            f"整体与{_tag_phrase(diagnosis.tags)}较为契合。"
        )

    return "\n".join(lines)


def generate_expert_advice(
    diagnosis: PlanDiagnosis,
    llm: LLMClient | None = None,
) -> str:
    """
    生成行程专家建议。

    有 LLM：按 Role 提示词扩写；无 LLM：模板兜底。
    """
    if llm is None:
        return expand_with_template(diagnosis)

    user_payload = json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2)
    user = PLAN_ADVISOR_USER_TEMPLATE.format(payload=user_payload)
    return llm.complete(PLAN_ADVISOR_SYSTEM, user).strip()


def generate_plan_advice(
    metrics: PlanMetrics,
    llm: LLMClient | None = None,
) -> tuple[PlanDiagnosis, str]:
    """方案生成入口：metrics → 诊断 → 专家建议文案。"""
    diagnosis = diagnose_plan(metrics)
    advice = generate_expert_advice(diagnosis, llm)
    return diagnosis, advice
