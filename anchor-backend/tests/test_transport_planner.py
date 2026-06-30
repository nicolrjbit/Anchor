"""出行方式推荐与应用测试。"""

import unittest

from anchor.plan_builder import build_flipbook_plan
from anchor.state_machine import Session
from anchor.slots import Slots
from anchor.states import State
from anchor.transport_planner import (
    MODE_FACTOR,
    TRANSPORT_MODES,
    apply_transport_modes,
    extract_transport_legs,
    merge_transport_selections,
    recommend_mode,
)


class TestTransportPlanner(unittest.TestCase):
    def _session(self, **overrides) -> dict:
        slot_kw = dict(
            destination="重庆",
            days=2,
            anchor="玩",
            tags=["年轻情侣/朋友"],
        )
        slot_kw.update({k: v for k, v in overrides.items() if k in ("destination", "days", "anchor", "tags")})
        session_kw = {k: v for k, v in overrides.items() if k not in slot_kw}
        slots = Slots(**slot_kw)
        session = Session(
            current_state=State.CONVERGENCE,
            slots=slots,
            conflict_detail={"fatigue_score": 32},
            pace_modifier="normal",
            **session_kw,
        )
        return session.to_dict()

    def test_five_modes_defined(self):
        self.assertEqual(len(TRANSPORT_MODES), 5)
        self.assertIn("公交", MODE_FACTOR)

    def test_recommend_cross_hotel_low_stamina(self):
        mode, reason = recommend_mode(
            distance_km=2.5,
            db_mode=None,
            tags=["带长辈/银发"],
            from_type="玩",
            to_type="住",
        )
        self.assertIn(mode, TRANSPORT_MODES)
        self.assertIn("切换", reason)

    def test_plan_includes_transport_legs(self):
        plan = build_flipbook_plan(self._session())
        self.assertIn("transport_legs", plan)
        self.assertGreater(len(plan["transport_legs"]), 0)
        leg = plan["transport_legs"][0]
        self.assertIn("recommended_mode", leg)
        self.assertIn("selected_mode", leg)
        self.assertIn(leg["recommended_mode"], TRANSPORT_MODES)

    def test_apply_user_transport_modes(self):
        plan = build_flipbook_plan(self._session())
        legs = plan["transport_legs"]
        leg_id = legs[0]["leg_id"]
        overrides = {leg_id: "步行"}
        merged = merge_transport_selections(legs, overrides)
        updated = apply_transport_modes(plan, merged)
        node = next(
            n for d in updated["days"] for n in d["timeline"] if n.get("leg_id") == leg_id
        )
        self.assertEqual(node["tran_mode"], "步行")

    def test_recommend_with_metro_walk_preference(self):
        mode, reason = recommend_mode(
            distance_km=3.0,
            db_mode=None,
            tags=["年轻情侣/朋友"],
            from_type="玩",
            to_type="玩",
            preferred_modes=["地铁", "步行"],
        )
        self.assertEqual(mode, "地铁")
        self.assertIn("地铁加步行", reason)

    def test_recommend_with_drive_preference(self):
        mode, reason = recommend_mode(
            distance_km=5.0,
            db_mode=None,
            tags=["年轻情侣/朋友"],
            from_type="玩",
            to_type="玩",
            preferred_modes=["自驾"],
        )
        self.assertEqual(mode, "自驾")
        self.assertIn("自驾/租车", reason)

    def test_plan_defaults_to_slot_transport_preferences(self):
        session = self._session()
        session["transport_preferences"] = []
        session["slots"]["transport_preferences"] = ["自驾"]
        plan = build_flipbook_plan(session, use_cache=False)
        self.assertEqual(plan.get("transport_preference_label"), "自驾/租车")
        long_leg = next(
            (leg for leg in plan["transport_legs"] if leg.get("distance_km", 0) > 1),
            plan["transport_legs"][0],
        )
        self.assertEqual(long_leg["recommended_mode"], "自驾")
        self.assertIn("自驾/租车", long_leg.get("reason") or "")

    def test_selected_anchor_poi_in_plan(self):
        plan = build_flipbook_plan(self._session(), use_cache=False)
        first_play = plan["days"][0]["timeline"][0]
        session = self._session(
            selected_anchor_poi={
                "poi_id": first_play["poi_id"],
                "name": first_play["name"],
                "poi_type": first_play["type"],
            }
        )
        plan_picked = build_flipbook_plan(session, use_cache=False)
        self.assertEqual(plan_picked["selected_anchor_poi"]["poi_id"], first_play["poi_id"])


if __name__ == "__main__":
    unittest.main()
