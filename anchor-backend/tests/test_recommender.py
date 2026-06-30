"""推荐公式与策略单元测试。"""

import unittest

from anchor.recommender import (
    calc_attract_cost,
    calc_fatigue_index,
    calc_luggage_cost,
    calc_matching_score,
    calc_tran_cost,
    PoiCandidate,
    rank_fill_candidates,
    rank_follow_candidates,
)


class TestFormulas(unittest.TestCase):
    def test_matching_score(self):
        self.assertAlmostEqual(calc_matching_score(4.8, 1.2), 5.76)

    def test_tran_cost(self):
        self.assertAlmostEqual(calc_tran_cost(30, 1.2), 36.0)

    def test_attract_cost(self):
        self.assertAlmostEqual(calc_attract_cost(2.5, 3.0), 7.5)

    def test_luggage_cost(self):
        self.assertEqual(calc_luggage_cost(2), 40)

    def test_fatigue_index(self):
        idx = calc_fatigue_index([36, 20], [7.5, 2], luggage_count=1)
        self.assertAlmostEqual(idx, 36 + 20 + 7.5 + 2 + 20)


class TestRecommendationStrategy(unittest.TestCase):
    def test_follow_top3_by_score_minus_tran(self):
        candidates = [
            PoiCandidate("a", "play", "A", 5.0, 0, 0, matching_tag=1.0, tran_time=10, tran_factor=2),
            PoiCandidate("b", "play", "B", 4.5, 0, 0, matching_tag=1.0, tran_time=5, tran_factor=2),
            PoiCandidate("c", "play", "C", 4.0, 0, 0, matching_tag=1.0, tran_time=2, tran_factor=2),
        ]
        top = rank_follow_candidates(candidates, top_n=2)
        self.assertEqual(top[0].poi.poi_id, "c")  # 5.0 - 4 = 1.0? wait C: 4 - 4 = 0, B: 4.5-10=-5.5, A: 5-20=-15
        # C: matching 4, tran 4, follow 0
        # B: 4.5 - 10 = -5.5
        # A: 5 - 20 = -15
        # order: c, b, a
        self.assertEqual([t.poi.poi_id for t in top], ["c", "b"])

    def test_fill_filters_rating_and_radius(self):
        candidates = [
            PoiCandidate("x", "eat", "X", 4.8, 0, 0, distance_km=1.0),
            PoiCandidate("y", "eat", "Y", 4.5, 0, 0, distance_km=1.0),
            PoiCandidate("z", "eat", "Z", 4.9, 0, 0, distance_km=2.0),
        ]
        top = rank_fill_candidates(candidates, top_n=2)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].poi.poi_id, "x")


if __name__ == "__main__":
    unittest.main()
