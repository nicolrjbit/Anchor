import unittest

from anchor.fatigue import (
    POI_TO_ANCHOR_CAPACITY_SCALE,
    evaluate_fatigue,
    fatigue_display_score,
    poi_capacity_to_anchor,
)
from anchor.slots import Slots


class TestFatigueCalibration(unittest.TestCase):
    def test_poi_to_anchor_scale(self):
        self.assertEqual(poi_capacity_to_anchor(50), 5.0)
        self.assertEqual(poi_capacity_to_anchor(180), 18.0)
        self.assertEqual(POI_TO_ANCHOR_CAPACITY_SCALE, 10.0)

    def test_elderly_play_conflict(self):
        result = evaluate_fatigue(
            Slots(
                destination="南京",
                days=3,
                anchor="玩",
                tags=["带长辈出行"],
            )
        )
        self.assertTrue(result.has_conflict)
        self.assertAlmostEqual(result.user_capacity, 5.0)

    def test_relaxed_low_load_ok(self):
        result = evaluate_fatigue(
            Slots(
                destination="南京",
                days=2,
                anchor="吃",
                tags=["上班族"],
            )
        )
        self.assertFalse(result.has_conflict)
        score = fatigue_display_score(result)
        self.assertGreaterEqual(score, 15)
        self.assertLessEqual(score, 35)

    def test_score_spreads_across_100_scale(self):
        easy = evaluate_fatigue(
            Slots(
                destination="重庆",
                days=1,
                anchor="吃",
                tags=["大学生/年轻毕业生"],
            ),
            pace_modifier="relaxed",
        )
        moderate = evaluate_fatigue(
            Slots(
                destination="重庆",
                days=5,
                anchor="玩",
                tags=["年轻情侣/朋友"],
            ),
        )
        heavy = evaluate_fatigue(
            Slots(
                destination="重庆",
                days=10,
                anchor="玩",
                tags=["带长辈出行"],
            ),
        )
        extreme = evaluate_fatigue(
            Slots(
                destination="重庆",
                days=14,
                anchor="玩",
                tags=["带长辈出行"],
            ),
            pace_modifier="compact",
        )

        easy_score = fatigue_display_score(easy)
        moderate_score = fatigue_display_score(moderate)
        heavy_score = fatigue_display_score(heavy)
        extreme_score = fatigue_display_score(extreme)

        self.assertLessEqual(easy_score, 15)
        self.assertGreaterEqual(moderate_score, 55)
        self.assertLessEqual(moderate_score, 85)
        self.assertGreaterEqual(heavy_score, 90)
        self.assertGreaterEqual(extreme_score, 90)
        self.assertLessEqual(extreme_score, 99)
        self.assertLess(easy_score, moderate_score)
        self.assertLess(moderate_score, heavy_score)


if __name__ == "__main__":
    unittest.main()
