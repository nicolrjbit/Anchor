import unittest

from anchor.day_advisor import build_day_diagnosis
from anchor.plan_builder import build_flipbook_plan
from anchor.plan_diagnosis import PlanDayMetrics, PlanMetrics
from anchor.state_machine import Session
from anchor.slots import Slots
from anchor.states import State


class TestDayAdvisor(unittest.TestCase):
    def test_day_text_mentions_poi_name(self):
        timeline = [
            {"time": "09:30", "type": "玩", "name": "洪崖洞民俗风貌区", "tier": "中级"},
            {"time": "12:00", "type": "吃", "name": "珮姐老火锅（洪崖洞店）", "cuisine": "重庆火锅"},
        ]
        metrics = PlanMetrics(
            destination="重庆",
            days=3,
            anchor="玩",
            tags=["亲子游出行"],
            day_metrics=[
                PlanDayMetrics(day_index=1, matching_scores=[88], fatigue_index=40)
            ],
        )
        block = build_day_diagnosis(
            day_index=1,
            total_days=3,
            destination="重庆",
            tags=["亲子游出行"],
            anchor="玩",
            timeline=timeline,
            day_metrics=metrics.day_metrics[0],
            metrics=metrics,
        )
        pro = block["pros"][0]["standard_text"]
        self.assertIn("洪崖洞民俗风貌区", pro)
        self.assertIn("珮姐老火锅", pro)

    def test_flipbook_days_have_distinct_advice(self):
        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(
                destination="重庆",
                days=3,
                anchor="玩",
                tags=["年轻情侣/朋友"],
            ),
        ).to_dict()
        plan = build_flipbook_plan(session, use_cache=False)
        texts = [d["pros"][0]["standard_text"] for d in plan["days"]]
        self.assertEqual(len(texts), 3)
        self.assertEqual(len(set(texts)), 3)

    def _cq_plan(self, tags):
        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(destination="重庆", days=3, anchor="玩", tags=tags),
        ).to_dict()
        return build_flipbook_plan(session, use_cache=False)

    def test_cons_not_uniformly_heavy_tran(self):
        """核心诉求：缺陷不再每天都是车乏感重，而是按当天动线分化。"""
        plan = self._cq_plan(["年轻情侣/朋友"])
        keys = [d["cons"][0]["rule_key"] for d in plan["days"] if d["cons"]]
        self.assertEqual(len(keys), 3)
        # 不再千篇一律
        self.assertGreater(len(set(keys)), 1)
        # 旧的「车乏感重」恒触发已消失
        self.assertNotIn("heavy_tran", keys)

    def test_clustering_keeps_downtown_days_tight(self):
        """聚类后市区日单段里程不应再出现上百公里的反方向折返。"""
        plan = self._cq_plan(["年轻情侣/朋友"])
        max_legs = []
        for d in plan["days"]:
            legs = [n.get("leg_distance_km", 0) for n in d["timeline"]]
            max_legs.append(max(legs) if legs else 0)
        # 至少有一天是紧凑市区团（单段 < 20km）
        tight_days = [m for m in max_legs if m < 20]
        self.assertGreaterEqual(len(tight_days), 1)

    def test_far_daytrip_flagged_as_long_transfer(self):
        """含跨城远点（大足/武隆）的那天应判为跨城一日游，而非泛泛车乏感。"""
        plan = self._cq_plan(["年轻情侣/朋友"])
        con_keys = [d["cons"][0]["rule_key"] for d in plan["days"] if d["cons"]]
        self.assertIn("long_transfer", con_keys)
        long_day = next(
            d for d in plan["days"] if d["cons"] and d["cons"][0]["rule_key"] == "long_transfer"
        )
        self.assertIn("公里", long_day["cons"][0]["standard_text"])

    def test_realistic_intercity_minutes(self):
        """跨城百公里不应再被估成数百分钟车程。"""
        from anchor.plan_builder import _fallback_tran_minutes

        self.assertLess(_fallback_tran_minutes(100), 180)
        self.assertGreater(_fallback_tran_minutes(100), 60)
        # 市内短途仍然合理
        self.assertLess(_fallback_tran_minutes(2), 20)

    def test_xinjiang_remote_plays_not_paired_same_day(self):
        """大区域远点（如赛里木湖、帕米尔）不应同日配对。"""
        from anchor.plan_builder import _haversine_km

        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(
                destination="新疆",
                days=5,
                anchor="玩",
                tags=["年轻情侣/朋友"],
            ),
        ).to_dict()
        plan = build_flipbook_plan(session, use_cache=False)
        remote_ids = {"xj_play_sailimu", "xj_play_pamir", "xj_play_kanas", "xj_play_hesu"}

        for day in plan["days"]:
            plays = [
                n
                for n in day["timeline"]
                if n.get("type") == "玩" and n.get("poi_id") in remote_ids
            ]
            if len(plays) >= 2:
                a, b = plays[0], plays[1]
                dist = _haversine_km(a["lng"], a["lat"], b["lng"], b["lat"])
                self.assertLess(dist, 200, f"同日远点相距 {dist:.0f}km: {a['name']} + {b['name']}")


if __name__ == "__main__":
    unittest.main()
