"""Flipbook 路书生成测试。"""

import unittest

from anchor.plan_builder import build_flipbook_plan, build_plan_shell
from anchor.transport_mapping import resolve_session_transport_preferences
from anchor.state_machine import Session
from anchor.slots import Slots
from anchor.states import State


class TestPlanBuilder(unittest.TestCase):
    def _session(self, **overrides) -> dict:
        defaults = dict(
            destination="重庆",
            days=2,
            anchor="玩",
            tags=["年轻情侣/朋友"],
            transport_preferences=["地铁", "步行"],
        )
        defaults.update(overrides)
        slots = Slots(**defaults)
        session = Session(
            current_state=State.CONVERGENCE,
            slots=slots,
            conflict_detail={"fatigue_score": 32},
            pace_modifier="relaxed",
        )
        return session.to_dict()

    def test_build_plan_shell_fast(self):
        shell = build_plan_shell(self._session())
        self.assertTrue(shell.get("shell"))
        self.assertEqual(len(shell["days"]), 2)
        self.assertIsNone(shell["cover"]["total_commute_km"])

    def test_resolve_transport_preferences_from_slots(self):
        session = self._session()
        session["transport_preferences"] = []
        self.assertEqual(
            resolve_session_transport_preferences(session),
            ["地铁", "步行"],
        )

    def test_build_chongqing_plan(self):
        plan = build_flipbook_plan(self._session())
        self.assertIn("cover", plan)
        self.assertEqual(plan["cover"]["title"], "重庆2日游")
        self.assertEqual(len(plan["days"]), 2)
        self.assertGreater(plan["cover"]["total_commute_km"], 0)
        self.assertIn("transport_legs", plan)
        day1 = plan["days"][0]
        self.assertGreaterEqual(len(day1["timeline"]), 3)
        self.assertGreaterEqual(len(day1["route"]), 3)
        self.assertTrue(day1["pros"])
        node_with_leg = next(n for n in day1["timeline"] if n.get("leg_id"))
        self.assertIn("poi_id", node_with_leg)

    def test_anchor_eat_order(self):
        plan = build_flipbook_plan(
            self._session(anchor="吃", tags=["大学生/年轻毕业生"])
        )
        first = plan["days"][0]["timeline"][0]
        self.assertEqual(first["type"], "吃")

    def test_event_mode_one_day_light_timeline(self):
        session = self._session(days=5)
        session["p1_mode"] = "EVENT"
        session["travel_mode"] = "route_light"
        plan = build_flipbook_plan(session, use_cache=False)
        self.assertEqual(len(plan["days"]), 1)
        self.assertEqual(plan["cover"]["title"], "重庆1日游")
        day = plan["days"][0]
        self.assertLessEqual(len(day["timeline"]), 4)

    def test_chengdu_plan_builds(self):
        plan = build_flipbook_plan(
            self._session(destination="成都", days=3), use_cache=False
        )
        self.assertEqual(plan["cover"]["destination"], "成都")
        self.assertEqual(len(plan["days"]), 3)

    def test_xian_plan_builds(self):
        plan = build_flipbook_plan(
            self._session(destination="西安", days=3), use_cache=False
        )
        self.assertEqual(plan["cover"]["destination"], "西安")
        self.assertGreater(plan["cover"]["total_commute_km"], 0)


if __name__ == "__main__":
    unittest.main()
