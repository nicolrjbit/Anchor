"""用户画像标签与劳累度上限解析（对齐 db/init_db.TAG_ALIAS）。"""

from __future__ import annotations

import re

# 映射表 canonical 用户画像（生成方案前必须采集其一）
PROFILE_TAGS = frozenset(
    {
        "大学生/年轻毕业生",
        "追星族/赛事爱好者",
        "年轻情侣/朋友",
        "长途长假游客",
        "单身独居青年",
        "上班族",
        "商务出差",
        "亲子游出行",
        "带长辈出行",
    }
)

# 口语/旧称 → canonical 用户画像（仅同义改写，不含偏好词）
PROFILE_SYNONYMS: dict[str, str] = {
    "带长辈": "带长辈出行",
    "长辈出行": "带长辈出行",
    "亲子游": "亲子游出行",
    "亲子游家庭": "亲子游出行",
}

# 对话/偏好词 → 映射表 user_tag（仅用于疲劳度/POI 匹配，不写入 slots.tags）
TAG_ALIAS: dict[str, str] = {
    **PROFILE_SYNONYMS,
    "特种兵": "大学生/年轻毕业生",
    "景点打卡": "长途长假游客",
    "行程节奏紧凑": "大学生/年轻毕业生",
    "酒店度假": "上班族",
    "行程节奏宽松": "上班族",
    "控制劳累度": "带长辈出行",
    "美食寻味": "年轻情侣/朋友",
    "周末出行": "年轻情侣/朋友",
    "短途": "单身独居青年",
    "固定时间": "追星族/赛事爱好者",
    "轻度打卡": "商务出差",
}

# slots canonical → DB 映射表 user_tag
DB_USER_TAG: dict[str, str] = {
    "亲子游出行": "亲子游家庭",
}

USER_FATIGUE_MAX: dict[str, float] = {
    "大学生/年轻毕业生": 180,
    "追星族/赛事爱好者": 160,
    "年轻情侣/朋友": 140,
    "长途长假游客": 120,
    "单身独居青年": 110,
    "上班族": 100,
    "商务出差": 90,
    "亲子游出行": 80,
    "亲子游家庭": 80,
    "带长辈出行": 50,
}

# 口语 → 标准用户画像
PROFILE_TAG_PHRASES: list[tuple[str, str]] = [
    (r"大学生|在校生|年轻毕业生|刚毕业|学生党|同学(?:一起|结伴)", "大学生/年轻毕业生"),
    (r"追星|看演唱会|看比赛|赛事|球迷|音乐节|追(?:星|现场)", "追星族/赛事爱好者"),
    (r"情侣|和对象|男朋友|女朋友|闺蜜|朋友一起|和朋友|姐妹|女朋友", "年轻情侣/朋友"),
    (r"长假|假期很长|连着休|连休|大假|休\d+天", "长途长假游客"),
    (r"一个人|独自|自己(?:一个|人)(?:玩|逛|去)|单身", "单身独居青年"),
    (r"上班族|打工人|上班(?:族)?|通勤", "上班族"),
    (r"出差|商务(?:出行|差旅)?|顺路(?:玩|逛|看看)", "商务出差"),
    (r"亲子|带娃|带孩子|有娃|宝宝|小孩|家人一起", "亲子游出行"),
    (
        r"(?:我)?带(?:着|上)?(?:父母|爸妈|长辈|老人|爷奶)|陪(?:爸|妈|父母|长辈|老人)",
        "带长辈出行",
    ),
]

# 映射表2：硬核打卡类标签
HARDCORE_TAGS = frozenset(
    {"特种兵", "景点打卡", "行程节奏紧凑", "长途长假游客", "大学生/年轻毕业生"}
)

# 映射表2：带娃/陪长辈/躺平类标签
LOW_STAMINA_TAGS = frozenset(
    {
        "亲子游",
        "亲子游家庭",
        "亲子游出行",
        "带长辈",
        "长辈出行",
        "控制劳累度",
        "酒店度假",
        "行程节奏宽松",
        "上班族",
        "商务出差",
        "轻度打卡",
        "带长辈出行",
    }
)


def normalize_profile_tag(tag: str) -> str | None:
    text = tag.strip()
    if not text:
        return None
    if text in PROFILE_TAGS:
        return text
    mapped = PROFILE_SYNONYMS.get(text)
    if mapped in PROFILE_TAGS:
        return mapped
    return None


def resolve_profile_tags(tags: list[str]) -> list[str]:
    """只接受九个 canonical 及其口语同义词，偏好词一律丢弃。"""
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        mapped = normalize_profile_tag(tag)
        if mapped and mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


def sanitize_profile_tags(tags: list[str]) -> list[str]:
    """slots.tags 只允许九个 canonical 用户画像。"""
    return list(dict.fromkeys(t for t in tags if t in PROFILE_TAGS))


def has_profile_tag(tags: list[str]) -> bool:
    """仅 canonical 用户画像算采集完成。"""
    return any(tag in PROFILE_TAGS for tag in tags)


def extract_profile_tags(text: str) -> list[str]:
    """从用户消息提取 canonical 用户画像。"""
    return infer_profile_tags(text)


def infer_profile_tags(text: str) -> list[str]:
    found: list[str] = []
    for pattern, profile in PROFILE_TAG_PHRASES:
        if re.search(pattern, text):
            found.append(profile)
    return list(dict.fromkeys(found))


def db_user_tag(tag: str) -> str:
    """查询 POI/映射表时，将 slots 标签转为 DB user_tag。"""
    return DB_USER_TAG.get(tag, tag)


def resolve_fatigue_max(tags: list[str]) -> float:
    """多标签取最严格（最小）上限。"""
    mapped = resolve_profile_tags(tags)
    limits = [
        USER_FATIGUE_MAX[db_user_tag(t)]
        for t in mapped
        if db_user_tag(t) in USER_FATIGUE_MAX
    ]
    return min(limits) if limits else 100.0


def has_hardcore_tag(tags: list[str]) -> bool:
    expanded = set(tags) | set(resolve_profile_tags(tags))
    return bool(expanded & HARDCORE_TAGS)


def has_low_stamina_tag(tags: list[str]) -> bool:
    expanded = set(tags) | set(resolve_profile_tags(tags))
    return bool(expanded & LOW_STAMINA_TAGS)
