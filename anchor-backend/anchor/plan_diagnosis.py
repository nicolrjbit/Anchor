"""方案优缺点诊断 — 规则来自 映射表2.md"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from anchor.recommender import LUGGAGE_UNIT_COST
from anchor.tag_mapping import (
    has_hardcore_tag,
    has_low_stamina_tag,
    resolve_fatigue_max,
)

Category = Literal["pro", "con"]

# 触发阈值（映射表2）
AVG_MATCHING_PRO = 85.0
AVG_MATCHING_CON = 60.0
TRAN_RATIO_PRO = 0.20
TRAN_RATIO_CON = 0.40
TRAN_ABSOLUTE_HIGH = 50.0
FATIGUE_RELAX_RATIO = 0.70
ATTRACT_HIGH_RATIO = 0.45
LUGGAGE_CON_THRESHOLD = LUGGAGE_UNIT_COST * 2  # 换房两次以上


@dataclass
class MustVisitPoi:
    name: str
    matching_score: float
    is_must_visit: bool = True


@dataclass
class PlanDayMetrics:
    day_index: int
    matching_scores: list[float] = field(default_factory=list)
    must_visit_pois: list[MustVisitPoi] = field(default_factory=list)
    tran_cost: float = 0.0
    attract_cost: float = 0.0
    fatigue_index: float = 0.0


@dataclass
class PlanMetrics:
    destination: str
    days: int
    anchor: str
    tags: list[str]
    day_metrics: list[PlanDayMetrics] = field(default_factory=list)
    luggage_count: int = 0
    fatigue_max: float | None = None

    def __post_init__(self) -> None:
        if self.fatigue_max is None:
            self.fatigue_max = resolve_fatigue_max(self.tags)

    @property
    def luggage_cost(self) -> float:
        return LUGGAGE_UNIT_COST * self.luggage_count

    def all_matching_scores(self) -> list[float]:
        scores: list[float] = []
        for day in self.day_metrics:
            scores.extend(day.matching_scores)
        return scores


@dataclass
class DiagnosisItem:
    rule_key: str
    dimension: str
    category: Category
    standard_text: str
    preset_tip: str | None = None
    day_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_key": self.rule_key,
            "dimension": self.dimension,
            "category": self.category,
            "standard_text": self.standard_text,
            "preset_tip": self.preset_tip,
            "day_index": self.day_index,
        }


@dataclass
class PlanDiagnosis:
    destination: str
    days: int
    anchor: str
    tags: list[str]
    pros: list[DiagnosisItem] = field(default_factory=list)
    cons: list[DiagnosisItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "days": self.days,
            "anchor": self.anchor,
            "tags": self.tags,
            "pros": [p.to_dict() for p in self.pros],
            "cons": [c.to_dict() for c in self.cons],
        }


# 映射表2 标准描述文案
PRO_COPY: dict[str, str] = {
    "high_matching": "【高纯度量身定制】：行程内的景点/餐厅与您的个人偏好契合度极高，闭眼冲不踩雷。",
    "low_tran_ratio": "【高含金量行程】：通勤时间被压缩到极致，把宝贵的时间都留给景区，而不是浪费在路上。",
    "no_luggage": "【行李零负担 / 一住到底】：全程无需打包行李、办理退换房，像本地人一样松弛度假。",
    "hardcore_full": "【硬核充实，值回票价】：游玩时间拉满，专为精力充沛的您设计，绝对玩得尽兴。",
    "relaxed_pace": "【高电量松弛感】：整体能耗极低，节奏温和，游玩结束后依然精力充沛，老少皆宜。",
}

CON_COPY: dict[str, str] = {
    "low_matching_must": "【局部体验可能踩雷】：行程中包含了个别与您标签匹配度较低的盲盒点，可能不符合您的预期。",
    "heavy_tran": "【市内通勤偏多】：今日点位之间换乘较密，路上零碎时间加起来不算短。",
    "long_transfer": "【跨城一日游 · 车程偏长】：今日有一段约 {km} 公里的城际往返，光在路上单程就得不少时间。",
    "backtrack": "【动线有回头路】：今日路线中途折返了一段，会多走一截冤枉路。",
    "frequent_hotel": "【中途频繁换房，略显折腾】：需要收拾多次行李并配合退改房时间，会碎裂掉一部分早晨的时间。",
    "heavy_attract": "【景点耗能过大，不宜硬撑】：部分景区游玩时间过长（如大范围步行/爬坡），长辈或宝宝容易电量耗尽。",
    "fatigue_over": "【今日强度偏高，体力要留余】：景点与赶路叠加，晚上大概率会比较累。",
}

CON_TIPS: dict[str, str] = {
    "low_matching_must": "对匹配度偏低的点，建议降低心理预期，或预留一顿轻松下午茶作为备选。",
    "heavy_tran": "把同片区的点排在一起，提前查好换乘，零碎通勤能省下不少。",
    "long_transfer": "把这天当作专门的一日游，别再额外加点；备颈枕和晕车药，错峰出发避开堵车。",
    "backtrack": "按地图顺序串成单向动线，把同方向的点放在一起，少走回头路。",
    "frequent_hotel": "换房前一晚把洗漱包和次日衣物单独装一个小袋，早晨能省下不少时间。",
    "heavy_attract": "带娃或陪长辈时，备折叠凳或婴儿推车，并预留午间回酒店歇脚的时间。",
    "fatigue_over": "穿一双真正跟脚的鞋，晚上留半小时泡脚，别排深夜加餐。",
}


def _tran_ratio(day: PlanDayMetrics) -> float:
    if day.fatigue_index <= 0:
        return 0.0
    return day.tran_cost / day.fatigue_index


def _attract_ratio(day: PlanDayMetrics) -> float:
    if day.fatigue_index <= 0:
        return 0.0
    return day.attract_cost / day.fatigue_index


def _append_unique(items: list[DiagnosisItem], item: DiagnosisItem) -> None:
    if any(x.rule_key == item.rule_key and x.day_index == item.day_index for x in items):
        return
    items.append(item)


def diagnose_plan(metrics: PlanMetrics) -> PlanDiagnosis:
    diagnosis = PlanDiagnosis(
        destination=metrics.destination,
        days=metrics.days,
        anchor=metrics.anchor,
        tags=metrics.tags,
    )
    fatigue_max = metrics.fatigue_max or 100.0

    # —— 优点：方案级平均推荐分 ——
    all_scores = metrics.all_matching_scores()
    if all_scores:
        avg_score = sum(all_scores) / len(all_scores)
        if avg_score >= AVG_MATCHING_PRO:
            _append_unique(
                diagnosis.pros,
                DiagnosisItem(
                    rule_key="high_matching",
                    dimension="matching_score",
                    category="pro",
                    standard_text=PRO_COPY["high_matching"],
                ),
            )

    # —— 优点：行李零负担 ——
    if metrics.luggage_count == 0:
        _append_unique(
            diagnosis.pros,
            DiagnosisItem(
                rule_key="no_luggage",
                dimension="luggage_cost",
                category="pro",
                standard_text=PRO_COPY["no_luggage"],
            ),
        )

    for day in metrics.day_metrics:
        tran_r = _tran_ratio(day)
        attract_r = _attract_ratio(day)

        # 优点：交通占比低
        if day.fatigue_index > 0 and tran_r < TRAN_RATIO_PRO:
            _append_unique(
                diagnosis.pros,
                DiagnosisItem(
                    rule_key="low_tran_ratio",
                    dimension="tran_cost",
                    category="pro",
                    standard_text=PRO_COPY["low_tran_ratio"],
                    day_index=day.day_index,
                ),
            )

        # 优点：硬核 + 高景点消耗
        if has_hardcore_tag(metrics.tags) and attract_r >= ATTRACT_HIGH_RATIO:
            _append_unique(
                diagnosis.pros,
                DiagnosisItem(
                    rule_key="hardcore_full",
                    dimension="attract_cost",
                    category="pro",
                    standard_text=PRO_COPY["hardcore_full"],
                    day_index=day.day_index,
                ),
            )

        # 优点：劳累度 <= 70% 上限
        if day.fatigue_index <= fatigue_max * FATIGUE_RELAX_RATIO:
            _append_unique(
                diagnosis.pros,
                DiagnosisItem(
                    rule_key="relaxed_pace",
                    dimension="fatigue_index",
                    category="pro",
                    standard_text=PRO_COPY["relaxed_pace"],
                    day_index=day.day_index,
                ),
            )

        # —— 缺点 ——
        for poi in day.must_visit_pois:
            if poi.is_must_visit and poi.matching_score < AVG_MATCHING_CON:
                _append_unique(
                    diagnosis.cons,
                    DiagnosisItem(
                        rule_key="low_matching_must",
                        dimension="matching_score",
                        category="con",
                        standard_text=CON_COPY["low_matching_must"],
                        preset_tip=CON_TIPS["low_matching_must"],
                        day_index=day.day_index,
                    ),
                )

        if day.fatigue_index > 0 and (
            tran_r > TRAN_RATIO_CON or day.tran_cost >= TRAN_ABSOLUTE_HIGH
        ):
            _append_unique(
                diagnosis.cons,
                DiagnosisItem(
                    rule_key="heavy_tran",
                    dimension="tran_cost",
                    category="con",
                    standard_text=CON_COPY["heavy_tran"],
                    preset_tip=CON_TIPS["heavy_tran"],
                    day_index=day.day_index,
                ),
            )

        if has_low_stamina_tag(metrics.tags) and attract_r >= ATTRACT_HIGH_RATIO:
            _append_unique(
                diagnosis.cons,
                DiagnosisItem(
                    rule_key="heavy_attract",
                    dimension="attract_cost",
                    category="con",
                    standard_text=CON_COPY["heavy_attract"],
                    preset_tip=CON_TIPS["heavy_attract"],
                    day_index=day.day_index,
                ),
            )

        if day.fatigue_index > fatigue_max:
            _append_unique(
                diagnosis.cons,
                DiagnosisItem(
                    rule_key="fatigue_over",
                    dimension="fatigue_index",
                    category="con",
                    standard_text=CON_COPY["fatigue_over"],
                    preset_tip=CON_TIPS["fatigue_over"],
                    day_index=day.day_index,
                ),
            )

    if metrics.luggage_cost >= LUGGAGE_CON_THRESHOLD:
        _append_unique(
            diagnosis.cons,
            DiagnosisItem(
                rule_key="frequent_hotel",
                dimension="luggage_cost",
                category="con",
                standard_text=CON_COPY["frequent_hotel"],
                preset_tip=CON_TIPS["frequent_hotel"],
            ),
        )

    return diagnosis
