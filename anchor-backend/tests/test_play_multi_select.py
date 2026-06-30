"""景点多选排期测试。"""

import unittest

from anchor.plan_builder import _build_play_schedule, build_flipbook_plan
from anchor.state_machine import Session
from anchor.slots import Slots
from anchor.states import State


class TestPlayMultiSelect(unittest.TestCase):
    def _session(self, selected_pois: list[dict], **slot_kw) -> dict:
        defaults = dict(destination="重庆", days=2, anchor="玩", tags=["年轻情侣/朋友"])
        defaults.update(slot_kw)
        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(**defaults),
            conflict_detail={"fatigue_score": 32},
            selected_anchor_pois=selected_pois,
            selected_anchor_poi=selected_pois[0] if selected_pois else None,
        )
        return session.to_dict()

    def test_multi_play_pois_all_appear_in_plan(self):
        selected = [
            {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
            {"poi_id": "cq_play_ciqikou", "name": "磁器口古镇", "poi_type": "玩"},
            {"poi_id": "cq_play_jiefangbei", "name": "解放碑步行街", "poi_type": "玩"},
        ]
        plan = build_flipbook_plan(self._session(selected), use_cache=False)
        play_names = {
            node["name"]
            for day in plan["days"]
            for node in day["timeline"]
            if node["type"] == "玩"
        }
        for pick in selected:
            self.assertIn(pick["name"], play_names)

    def test_multi_play_not_single_repeat_only(self):
        selected = [
            {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
            {"poi_id": "cq_play_ciqikou", "name": "磁器口古镇", "poi_type": "玩"},
        ]
        plan = build_flipbook_plan(self._session(selected), use_cache=False)
        play_names = [
            node["name"]
            for day in plan["days"]
            for node in day["timeline"]
            if node["type"] == "玩"
        ]
        self.assertGreater(len(set(play_names)), 1)

    def test_three_day_unique_play_per_day(self):
        plan = build_flipbook_plan(
            self._session(
                [
                    {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
                ],
                days=3,
            ),
            use_cache=False,
        )
        for day in plan["days"]:
            play_names = [n["name"] for n in day["timeline"] if n["type"] == "玩"]
            self.assertEqual(len(play_names), len(set(play_names)), day["day_index"])

    def test_hotel_schedule_minimizes_daily_travel(self):
        plan = build_flipbook_plan(
            self._session(
                [
                    {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
                    {"poi_id": "cq_play_ciqikou", "name": "磁器口古镇", "poi_type": "玩"},
                ],
                days=2,
            ),
            use_cache=False,
        )
        day_hotels = []
        for day in plan["days"]:
            hotels = [n for n in day["timeline"] if n["type"] == "住"]
            self.assertEqual(len(hotels), 1, day["day_index"])
            day_hotels.append(hotels[0]["name"])
        self.assertTrue(all(day_hotels), "每日应有落脚点")
        stay_node = next(n for n in plan["days"][0]["timeline"] if n["type"] == "住")
        self.assertIn("贴近今日动线", stay_node["detail"])

    def test_hotel_can_switch_when_play_areas_differ(self):
        from anchor.plan_builder import (
            _build_fatigue_optimized_hotel_schedule,
            _connect,
            _load_city_bundle,
        )

        order = ["玩", "吃", "玩", "吃", "住"]
        conn = _connect()
        try:
            pois, traffic, _ = _load_city_bundle(conn, "重庆", "上班族")
        finally:
            conn.close()
        play_pool = pois["玩"]
        by_id = {p.id: p for p in play_pool}
        play_schedule = {
            (1, 0): by_id["cq_play_hongyadong"],
            (1, 2): by_id["cq_play_jiefangbei"],
            (2, 0): by_id["cq_play_ciqikou"],
            (2, 2): by_id["cq_play_ciqikou"],
        }
        stay = _build_fatigue_optimized_hotel_schedule(
            2, order, [], pois["住"], play_schedule, {}, traffic
        )
        day1 = stay[(1, 4)].id
        day2 = stay[(2, 4)].id
        self.assertNotEqual(day1, day2)

    def test_five_day_unique_eat_per_day(self):
        plan = build_flipbook_plan(
            self._session(
                [
                    {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
                    {"poi_id": "cq_play_ciqikou", "name": "磁器口古镇", "poi_type": "玩"},
                ],
                days=5,
            ),
            use_cache=False,
        )
        all_eats: list[str] = []
        for day in plan["days"]:
            eats = [n["name"] for n in day["timeline"] if n["type"] == "吃"]
            self.assertEqual(len(eats), len(set(eats)), day["day_index"])
            all_eats.extend(eats)
        self.assertEqual(len(all_eats), len(set(all_eats)), "全程餐厅尽量不重复")

    def test_build_play_schedule_covers_all_selected(self):
        from anchor.plan_builder import PoiPoint, _load_city_bundle, _connect

        conn = _connect()
        try:
            pois, _, _ = _load_city_bundle(conn, "重庆", "上班族")
        finally:
            conn.close()
        pool = pois["玩"]
        selected = [pool[0], pool[1], pool[2]]
        schedule = _build_play_schedule(2, ["玩", "吃", "玩", "吃", "住"], selected, pool)
        scheduled_names = {p.name for p in schedule.values()}
        for poi in selected:
            self.assertIn(poi.name, scheduled_names)


if __name__ == "__main__":
    unittest.main()
