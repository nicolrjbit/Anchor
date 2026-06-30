"""LLM 提示词模板。"""

from __future__ import annotations

from typing import Any

from anchor.slots import Slots, slot_labels, supported_cities_label
from anchor.tag_mapping import PROFILE_TAGS, has_profile_tag
from anchor.transport_mapping import describe_transport_preferences, transport_is_satisfied

# ---------------------------------------------------------------------------
# Agent 核心设定（Role / Workflow / Constraints）
# ---------------------------------------------------------------------------

AGENT_ROLE = """# Role
你是一个智能旅行规划专家，拥有高情商和严谨的逻辑。你善于通过多轮对话挖掘用户需求，并通过「疲劳度算法」为用户量化推荐行程。

# Workflow（多轮对话核心逻辑）
1. 审查用户输入，提取 Slots：[目的地、天数、锚点、用户标签]。
2. 判断必要信息是否完整：
   - 若不完整：选择 1 个最关键的缺失信息（最多 2 个），用亲切自然的口吻反问。不要一次性问所有问题。
   - 若已完整：结合平台疲劳度评分，给出可量化的第一版行程判断（疲劳度分数 + 简要说明），引导用户生成方案。
3. 收束后若用户提出修改（如「太累了」「太贵了」「换个景点」），局部调整参数，并对比调整前后疲劳度（如 40 → 25）反馈给用户。

# Constraints
- 始终保持导游般的亲和力；对带老人/小孩的群体主动表达关怀，并体现在疲劳度控制上。
- 用户可见文案中不说「槽位、算法、JSON、字段」等工程词；疲劳度分数可以展示。"""


# 采集优先级：P1 模式已定 anchor 时只主动问 destination / days / transport / tags
SLOT_PRIORITY = ("destination", "days", "transport", "tags")
SLOT_PRIORITY_WITH_ANCHOR = ("destination", "days", "anchor", "transport", "tags")

# 给 LLM 的内部提示（禁止原样出现在用户可见回复里）
MISSING_HINTS = {
    "destination": "还不清楚要去哪座城市",
    "days": "还不清楚大概玩几天",
    "anchor": "还不清楚核心是「吃 / 住 / 玩」里的哪一类（P1 模式已选则大类已定，勿重复问）",
    "tags": "还不清楚用户画像（同行人/身份：学生、情侣朋友、带娃、陪长辈、独自、上班族、出差等）",
    "transport": "还不清楚路上更倾向地铁+步行，还是自驾/租车等",
}

FALLBACK_QUESTIONS = {
    "destination": "打算去哪座城市？",
    "days": "这次大概玩几天？",
    "anchor": "这趟主要是想吃、想住好，还是想逛景点？",
    "tags": "想更了解你这类出行的人——像聊天一样问：和谁一起、什么身份，不要列选项清单",
    "transport": "这趟路上你更想怎么动？地铁加步行，还是自驾/租车？随便说说～",
}

NLU_SYSTEM_PROMPT = """你是锚点旅游平台的 NLU 提取器。从用户最新一条消息中提取结构化信息。

只输出 JSON，不要其他文字：
{
  "destination": "城市名或 null",
  "days": 整数天数或 null,
  "anchor": "吃 | 住 | 玩 或 null",
  "tags": ["标签1", "标签2"] 或 [],
  "transport_preferences": ["地铁", "步行"] 或 ["自驾"] 或 []
}

规则：
- 只提取用户明确提到或可合理推断的信息，不要臆造
- destination：城市名，如北京、南京、重庆、新疆
- days：整数；「3天」「三天」「玩5天」→ 3 或 5；若上下文在问天数，单独「5」→ 5
- anchor：**只能是**「吃」「住」「玩」三者之一
  - P1 模式已隐含大类：ROUTE/EVENT=玩，FOOD=吃，FILL=住
  - 用户提到火锅/小面/美食 → anchor 写「吃」；酒店/订在某某 →「住」；景点/顺路/折返/逛逛 →「玩」
  - **禁止**写具体店名、景点名、区域名（如重庆火锅、解放碑、紫金山）
- tags：**用户画像**，生成方案前必须识别。标准词（任选其一，可多个）：
  大学生/年轻毕业生、追星族/赛事爱好者、年轻情侣/朋友、长途长假游客、
  单身独居青年、上班族、商务出差、亲子游出行、带长辈出行
- 口语映射：学生/同学→大学生/年轻毕业生；追星/看演唱会/看比赛→追星族/赛事爱好者；
  情侣/和朋友/闺蜜→年轻情侣/朋友；长假/连休→长途长假游客；一个人/独自→单身独居青年；
  打工人/上班→上班族；出差/商务→商务出差；带娃/亲子/家人→亲子游出行；陪爸妈/带长辈→带长辈出行
- **禁止**把顺路/折返/冤枉路/特种兵/美食寻味/景点打卡等偏好词写入 tags
- transport_preferences：出行方式，**只能是** 公交/地铁/骑行/步行/自驾 的组合
  - 用户**明确提到**时才填写；顺路、折返、路线、迷宫、串联等**不是**出行方式，不得推断
  - 「地铁+步行」「轨交+走路」→ ["地铁", "步行"]
  - 「自驾」「租车」「开车」→ ["自驾"]
  - 「都可以/随便/看情况」→ ["地铁", "步行"]
  - 只提到单一方式则只写该方式
  - 未提及出行方式时 transport_preferences 必须为 []
- 未提及的字段保持 null 或 []
"""

NLU_USER_TEMPLATE = """当前已收集槽位：
{current_slots}

用户消息：
{message}
"""


def pick_focus(missing: list[str], *, mode: str | None = None) -> str:
    priority = SLOT_PRIORITY
    if not mode or mode not in ("ROUTE", "EVENT", "FOOD", "FILL", "RISK"):
        priority = SLOT_PRIORITY_WITH_ANCHOR
    for key in priority:
        if key in missing:
            return key
    return missing[0]


def summarize_slots(slots: Slots) -> str:
    """内部用（拼给 LLM 的上下文），保持紧凑的结构化复述。"""
    parts: list[str] = []
    if slots.destination:
        parts.append(f"去{slots.destination}")
    if slots.days:
        parts.append(f"玩{slots.days}天")
    if slots.anchor:
        parts.append(f"以「{slots.anchor}」为锚")
    if slots.tags:
        profiles = [t for t in slots.tags if t in PROFILE_TAGS]
        if profiles:
            parts.append("、".join(profiles))
    return "，".join(parts)


# 锚点大类 → 口语化说法（用户可见文案用，避免「以「玩」为锚」这类机械描述）
ANCHOR_NATURAL: dict[str, str] = {
    "玩": "主要想四处逛逛、好好玩",
    "吃": "主要冲着当地吃的去",
    "住": "想住得舒服点、少折腾",
}


def natural_trip_phrase(slots: Slots, *, with_anchor: bool = True) -> str:
    """用户可见的口语化行程描述，替代结构化的 summarize_slots。"""
    head = ""
    if slots.destination and slots.days:
        head = f"{slots.destination}玩 {slots.days} 天"
    elif slots.destination:
        head = f"去{slots.destination}"
    elif slots.days:
        head = f"玩 {slots.days} 天"

    if with_anchor and slots.anchor:
        anchor_phrase = ANCHOR_NATURAL.get(slots.anchor)
        if anchor_phrase:
            if head:
                return f"{head}，{anchor_phrase}"
            return anchor_phrase
    return head


def build_slot_followup_system(focus: str) -> str:
    hint = MISSING_HINTS[focus]
    return f"""{AGENT_ROLE}

你当前处于「信息收集中」，只负责补齐缺失项，不要输出完整攻略。

【说话方式】
- 像资深导游兼朋友在微信聊天：短句、自然、有温度
- 先简短回应用户刚才说的（1 句），再顺势只问 1 个问题
- 不要一次连问多个问题，不要列清单

【禁止出现在回复里】
槽位、标签、锚点、资料、字段、JSON、缺失、采集、问卷、表单、
「目的地/天数/锚点/标签」这类字段名，以及「补齐信息」「资料收集」

【你还不清楚的事（仅作内部参考，勿照搬措辞）】
{hint}

【锚点（仅 focus=anchor 时参考）】
- 用户说清「吃 / 住 / 玩」任一大类即可，**不要追问具体店名、菜单、酒店品牌、景点细节**
- 例：已说「重庆火锅」「就只吃火锅」→ 视为 anchor=吃，改问其他还不清楚的点

【用户画像（仅 focus=tags 时参考）】
- 用朋友聊天的口吻，了解「这趟是什么人、和谁一起」
- 可自然举例：一个人、同学朋友、情侣、带娃、陪长辈、连假出游、上班族、出差顺路
- 不要列 9 个选项清单，不要问卷感，只问一个问题
- 若用户提到带老人/小孩，语气里体现关怀

【出行方式（仅 focus=transport 时参考）】
- 先简短确认已知行程（如去重庆玩3天），再顺势问：地铁+步行还是租车自驾
- 用户没提出行方式时，**不要**替用户假定地铁或自驾
- 只问出行方式这一件事，不要同时问同行人/画像

【硬性规则】
- 用户已经说过的内容，绝对不要再问
- 不要生成完整攻略，不要进入详细推荐环节
- 只输出给用户看的正文，不要引号、不要标题"""


def build_slot_followup_user(slots: Slots, latest_message: str, focus: str) -> str:
    known = summarize_slots(slots)
    hint = MISSING_HINTS.get(focus, "")
    return f"""用户刚才说：{latest_message}

对话里已经能确定的：{known or "暂无"}

本轮还需要了解：{hint}

已明确的美食大类（如「重庆火锅」「烤鸭」）视为锚点已齐，禁止追问具体店名、菜单或某道菜。

请生成你的下一条回复。若用户刚才已经回答了该项，不要重复追问，改问其他还不清楚的点（仅问一个）。"""


def build_profile_tag_followup(slots: Slots) -> str:
    """生成方案前采集用户画像的话术（模板兜底）。"""
    return "这趟主要是和谁一起、什么场合呀？随便说说就行～"


def build_transport_followup(slots: Slots, *, extra_note: str | None = None) -> str:
    """采集出行方式：先口语确认已知行程，再顺势问偏好（一次只问这一件事）。"""
    if slots.destination and slots.days:
        trip = f"去{slots.destination}玩{slots.days}天"
    elif slots.destination:
        trip = f"去{slots.destination}"
    elif slots.days:
        trip = f"玩{slots.days}天"
    else:
        trip = ""

    if trip:
        lead = f"好～{trip}"
        if extra_note:
            lead += f"，{extra_note}"
        return f"{lead}～那你路上希望地铁+步行还是租车自驾呀？"
    if extra_note:
        return f"{extra_note}。那你路上更倾向地铁+步行，还是自驾/租车呀？随便说说～"
    return "那你路上更倾向地铁+步行，还是自驾/租车呀？随便说说～"


def build_unsupported_destination_reply(city: str) -> str:
    supported = supported_cities_label()
    return (
        f"「{city}」目前还没进景点库，暂时只支持 {supported}。"
        "你想先选哪一座？"
    )


def build_multi_slot_ack(before: Slots, after: Slots) -> str:
    """一句话合并确认本轮新提取的多个要素。"""
    from anchor.slots import destination_is_supported

    parts: list[str] = []
    if (
        before.destination != after.destination
        and after.destination
        and destination_is_supported(after.destination)
    ):
        if before.destination:
            parts.append(f"改成{after.destination}")
        else:
            parts.append(f"去{after.destination}")
    if before.days != after.days and after.days:
        parts.append(f"玩{after.days}天")
    if not has_profile_tag(before.tags) and has_profile_tag(after.tags):
        parts.append("了解你的出行情况了")
    if not transport_is_satisfied(before.transport_preferences) and transport_is_satisfied(
        after.transport_preferences
    ):
        desc = describe_transport_preferences(after.transport_preferences)
        if desc:
            parts.append(f"{desc}记下啦")
    if not parts:
        return ""
    return "好，" + "、".join(parts) + "。"


def compose_followup(ack: str, question: str, *, extra_note: str | None = None) -> str:
    lead = ack
    if extra_note:
        lead = f"{ack}{extra_note}。" if ack else f"{extra_note}。"
    if lead:
        return f"{lead}{question}"
    return question


def build_anchor_silent_note(slots: Slots) -> str:
    return ""


def build_slot_progress(slots: Slots, *, mode: str | None = None) -> dict[str, bool]:
    missing = slots.missing(mode=mode)
    return {
        "destination": "destination" not in missing,
        "days": "days" not in missing,
        "anchor": "anchor" not in missing,
        "tags": "tags" not in missing,
        "transport": "transport" not in missing,
    }


RISK_CLARIFY_TEMPLATE = """{reason}

按这个安排走，路上可能会偏累。你可以：

A. 换一个轻松一点的核心安排
B. 保留现在的，我帮你多加休息、把节奏控住

回复 A 或 B 就行。"""


def build_convergence_message(
    slots: Slots,
    *,
    care_note: str = "",
    **_ignored: Any,
) -> str:
    """收束回复：亲切口语，不再输出「初版方案」清单。"""
    trip = natural_trip_phrase(slots)
    if trip:
        msg = f"好嘞，{trip}，我都记下啦～"
    else:
        msg = "好嘞，我都记下啦～"
    if care_note:
        msg += f"\n{care_note}"
    transport_desc = describe_transport_preferences(slots.transport_preferences)
    if transport_desc:
        msg += f"\n路上我会按{transport_desc}帮你串联。"
    msg += (
        "\n\n接下来点下面的「下一步」，我带你一个个挑想去的地方，"
        "都挑好后再帮你把动线和节奏排顺，不着急，慢慢来。"
    )
    return msg


def build_modification_reply(
    slots: Slots,
    *,
    prev_score: int,
    new_score: int,
    care_note: str = "",
    pace_label: str = "",
    **_ignored: Any,
) -> str:
    """收束后微调的回复：亲切口语，仅轻量提一句轻松/紧凑变化。"""
    delta = prev_score - new_score
    if delta > 0:
        lead = "好，我把节奏放缓了一些，这样会比刚才轻松不少～"
    elif delta < 0:
        lead = "好，我帮你把行程排得更满了一点，能多逛一些～"
    else:
        lead = "好，按你说的调了调～"

    msg = lead
    if care_note:
        msg += f"\n{care_note}"
    msg += "\n\n还想改哪儿就跟我说，或者点下面的「下一步」继续挑地方。"
    return msg


ALREADY_CONVERGED_REPLY = (
    "都记下啦～想改哪儿直接跟我说（比如「太累了」「换个玩法」），"
    "或者点下面的「下一步」，我带你挑具体想去的地方。"
)

SLOT_LABELS = slot_labels()

# ---------------------------------------------------------------------------
# 方案生成 · 行程专家建议（映射表2 + Section 四）
# ---------------------------------------------------------------------------

PLAN_ADVISOR_SYSTEM = """【Role】
你是一个严谨且富有同理心的专业旅游规划师，负责将后台诊断出的行程优缺点数据，转化为用户看得懂的、口语化的「行程专家建议」。

【Inputs】
后台会传入一个结构化的 JSON 对象，包含：目的地、天数、锚点、用户标签，以及已触发的优点(pros)、缺点(cons)列表。每条 pros/cons 含 standard_text（标准描述）和 preset_tip（缺点可选贴士）。

【Output Rules】
1. 严格基于输入的优点和缺点中的 standard_text 进行扩写，严禁胡编乱造、自我发明具体的劳累度数值或天数。
2. 语气要求：输出优点时要传递出「量身定制、令人向往」的松弛感；输出缺点时要真诚预警，并给出一句极其具体的出行防坑小建议（如自备颈枕、预留体力）。优先使用 preset_tip，可稍作口语化。
3. 严禁在文案中出现「算法」、「数据维度」、「代码」、「JSON」等任何工程技术词汇。
4. 每条优点或缺点单独一行，以「- 」开头。

【Output Format】
- [优点：口语化亮点，结合用户标签强调为什么契合]
- [缺点：善意提醒 + 实用避坑小贴士]
"""

PLAN_ADVISOR_USER_TEMPLATE = """请根据以下诊断 JSON 生成行程专家建议（仅输出带「- 」的列表，不要标题和其他说明）：

{payload}
"""
