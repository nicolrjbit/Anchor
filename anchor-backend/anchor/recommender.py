"""推荐公式与跟随/填充策略（无 POI 数据时可单元测试公式）。"""

from __future__ import annotations

from dataclasses import dataclass

# 填充策略：锚点周边半径（km）、最低评分
FILL_RADIUS_KM = 1.5
FILL_MIN_RATING = 4.6
FOLLOW_TOP_N = 3
FILL_TOP_N = 3
LUGGAGE_UNIT_COST = 20


@dataclass
class PoiCandidate:
    poi_id: str
    poi_type: str  # play | stay | eat
    name: str
    rating: float
    longitude: float
    latitude: float
    attract_time: float = 0.0
    attract_factor: float = 0.0
    matching_tag: float = 1.0
    tran_time: float = 0.0
    tran_factor: float = 1.0
    distance_km: float = 0.0


@dataclass
class ScoredRecommendation:
    poi: PoiCandidate
    matching_score: float
    tran_cost: float
    attract_cost: float
    follow_score: float
    rank: int


def calc_matching_score(rating: float, matching_tag: float) -> float:
    """matching_score = rating * matching_tag"""
    return rating * matching_tag


def calc_tran_cost(tran_time: float, tran_factor: float) -> float:
    """tran_cost = tran_time * tran_factor"""
    return tran_time * tran_factor


def calc_attract_cost(attract_time: float, attract_factor: float) -> float:
    """attract_cost = attract_time * attract_factor"""
    return attract_time * attract_factor


def calc_luggage_cost(luggage_count: int) -> float:
    """luggage_cost = 20 * luggage_count"""
    return LUGGAGE_UNIT_COST * luggage_count


def calc_fatigue_index(
    tran_costs: list[float],
    attract_costs: list[float],
    luggage_count: int = 0,
) -> float:
    """fatigue_index = Σ(tran_cost + attract_cost) + luggage_cost"""
    segment_sum = sum(t + a for t, a in zip(tran_costs, attract_costs))
    return segment_sum + calc_luggage_cost(luggage_count)


def rank_follow_candidates(
    candidates: list[PoiCandidate],
    *,
    top_n: int = FOLLOW_TOP_N,
) -> list[ScoredRecommendation]:
    """
    跟随策略：取 (matching_score - tran_cost) 最大的前 top_n 个。
    matching_score = rating * matching_tag
    """
    scored: list[ScoredRecommendation] = []
    for poi in candidates:
        matching_score = calc_matching_score(poi.rating, poi.matching_tag)
        tran_cost = calc_tran_cost(poi.tran_time, poi.tran_factor)
        attract_cost = calc_attract_cost(poi.attract_time, poi.attract_factor)
        follow_score = matching_score - tran_cost
        scored.append(
            ScoredRecommendation(
                poi=poi,
                matching_score=matching_score,
                tran_cost=tran_cost,
                attract_cost=attract_cost,
                follow_score=follow_score,
                rank=0,
            )
        )

    scored.sort(key=lambda x: x.follow_score, reverse=True)
    for i, item in enumerate(scored[:top_n], start=1):
        item.rank = i
    return scored[:top_n]


def rank_fill_candidates(
    candidates: list[PoiCandidate],
    *,
    top_n: int = FILL_TOP_N,
    min_rating: float = FILL_MIN_RATING,
    max_radius_km: float = FILL_RADIUS_KM,
) -> list[ScoredRecommendation]:
    """
    填充策略：锚点周边 max_radius_km 内，过滤 rating < min_rating，
    按 rating 降序取前 top_n。
    """
    filtered = [
        p
        for p in candidates
        if p.rating >= min_rating and p.distance_km <= max_radius_km
    ]
    filtered.sort(key=lambda p: p.rating, reverse=True)

    result: list[ScoredRecommendation] = []
    for i, poi in enumerate(filtered[:top_n], start=1):
        matching_score = calc_matching_score(poi.rating, poi.matching_tag)
        result.append(
            ScoredRecommendation(
                poi=poi,
                matching_score=matching_score,
                tran_cost=calc_tran_cost(poi.tran_time, poi.tran_factor),
                attract_cost=calc_attract_cost(poi.attract_time, poi.attract_factor),
                follow_score=0.0,
                rank=i,
            )
        )
    return result
