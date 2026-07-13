"""多轮对话与状态机单元测试。"""

import unittest

from anchor.dialogue_handler import handle_user_message
from anchor.slots import Slots
from anchor.state_machine import Session
from anchor.states import State


class TestDialogueHandler(unittest.TestCase):
    def test_init_to_slot_filling(self):
        session = Session()
        turn = handle_user_message(session, "你好")
        self.assertEqual(turn.session.current_state, State.SLOT_FILLING)
        self.assertIn("missing", turn.meta)

    def test_incremental_slot_collection(self):
        session = Session()
        t1 = handle_user_message(session, "想去南京")
        self.assertEqual(t1.session.current_state, State.SLOT_FILLING)
        self.assertEqual(t1.session.slots.destination, "南京")

        t2 = handle_user_message(t1.session, "玩3天")
        self.assertEqual(t2.session.slots.days, 3)

        t3 = handle_user_message(t2.session, "必去紫金山，带爸妈一起")
        self.assertEqual(t3.session.slots.anchor, "玩")
        self.assertIn("带长辈出行", t3.session.slots.tags)

    def test_profile_tag_question_before_convergence(self):
        session = Session()
        t1 = handle_user_message(
            session,
            "冲着重庆火锅去的",
            llm=None,
            mode="FOOD",
        )
        self.assertEqual(t1.session.slots.anchor, "吃")
        self.assertIn("days", t1.meta.get("missing", []))

        t2 = handle_user_message(t1.session, "5天", llm=None, mode="FOOD")
        self.assertIn("transport", t2.meta.get("missing", []))
        self.assertIn("地铁", t2.reply)

        t3 = handle_user_message(t2.session, "地铁加步行", llm=None, mode="FOOD")
        self.assertIn("tags", t3.meta.get("missing", []))
        self.assertIn("和谁一起", t3.reply)
        self.assertNotIn("场合", t3.reply)

        t4 = handle_user_message(t3.session, "和女朋友一起", llm=None, mode="FOOD")
        self.assertEqual(t4.session.current_state, State.CONVERGENCE)
        self.assertEqual(t4.session.slots.transport_preferences, ["地铁", "步行"])

    def test_food_anchor_category_without_restaurant_name(self):
        session = Session()
        session.slots = Slots(
            destination="重庆",
            days=5,
            tags=["年轻情侣/朋友"],
        )
        session.current_state = State.SLOT_FILLING

        turn = handle_user_message(session, "冲着重庆火锅去的", llm=None, mode="FOOD")
        self.assertEqual(turn.session.slots.anchor, "吃")
        self.assertNotIn("anchor", turn.meta.get("missing", []))

        turn2 = handle_user_message(turn.session, "就只吃重庆火锅", llm=None, mode="FOOD")
        self.assertEqual(turn2.session.slots.anchor, "吃")
        self.assertNotIn("anchor", turn.meta.get("missing", []))

    def test_p1_mode_implies_anchor_category_on_first_message(self):
        cases = [
            (
                "ROUTE",
                "我已经订好了去重庆的机票，听说那里的马路是立体迷宫。我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！",
                "玩",
            ),
            (
                "FOOD",
                "我想去重庆吃火锅，帮我推荐下重庆的酒店和景点。",
                "吃",
            ),
            (
                "FILL",
                "我已经定了酒店在重庆解放碑，帮我推荐下周围的景点。",
                "住",
            ),
            (
                "EVENT",
                "出差到重庆，想抽半天随便走走，帮我安排个轻松的行程。",
                "玩",
            ),
        ]
        for mode, message, expected_anchor in cases:
            with self.subTest(mode=mode):
                turn = handle_user_message(Session(), message, llm=None, mode=mode)
                self.assertEqual(turn.session.slots.destination, "重庆")
                self.assertEqual(turn.session.slots.anchor, expected_anchor)
                self.assertNotIn("anchor", turn.meta.get("missing", []))
                self.assertNotIn("景点打卡", turn.session.slots.tags)
                self.assertNotIn("美食寻味", turn.session.slots.tags)

    def test_fatigue_conflict_still_converges(self):
        session = Session()
        session.slots = Slots(
            destination="南京",
            days=3,
            anchor="玩",
            tags=["带长辈出行"],
            transport_preferences=["地铁", "步行"],
        )
        session.current_state = State.SLOT_FILLING

        turn = handle_user_message(session, "就这些")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)
        self.assertTrue(turn.session.has_conflict)
        self.assertIn("下一步", turn.reply)

    def test_convergence_is_warm_without_quantitative_plan(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(
            destination="南京",
            days=2,
            anchor="玩",
            tags=["年轻情侣/朋友"],
            transport_preferences=["地铁", "步行"],
        )
        turn = handle_user_message(session, "确认")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)
        # 不再输出「初版方案」清单与机械化的锚点措辞
        self.assertNotIn("第一版量化方案", turn.reply)
        self.assertNotIn("为锚", turn.reply)
        self.assertNotIn("为主线", turn.reply)
        self.assertNotIn("疲劳度", turn.reply)
        self.assertIn("下一步", turn.reply)
        # 后台仍计算锚点候选供 P3 使用
        self.assertTrue(turn.session.anchor_recommendations)

    def test_modification_keeps_warm_tone(self):
        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(
                destination="南京",
                days=3,
                anchor="玩",
                tags=["带长辈出行"],
                transport_preferences=["地铁", "步行"],
            ),
            has_conflict=True,
            conflict_detail={
                "estimated_load": 12,
                "user_capacity": 50,
                "has_conflict": True,
                "fatigue_score": 40,
            },
        )
        turn = handle_user_message(session, "太累了，轻松点")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)
        self.assertNotIn("调整后量化方案", turn.reply)
        self.assertNotIn("疲劳度", turn.reply)
        self.assertTrue(turn.reply.startswith("好，"))
        self.assertIn("下一步", turn.reply)
        self.assertEqual(turn.session.pace_modifier, "relaxed")

    def test_chongqing_route_dialogue_no_repeat_days_or_sightseeing(self):
        msg1 = (
            "我已经订好了去重庆的机票，听说那里的马路是立体迷宫。"
            "我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！"
        )
        t1 = handle_user_message(Session(), msg1, llm=None, mode="ROUTE")
        self.assertEqual(t1.session.slots.destination, "重庆")
        self.assertEqual(t1.session.slots.anchor, "玩")
        self.assertNotIn("anchor", t1.meta.get("missing", []))
        self.assertIn("days", t1.meta.get("missing", []))

        t2 = handle_user_message(t1.session, "5", llm=None, mode="ROUTE")
        self.assertEqual(t2.session.slots.days, 5)
        self.assertNotIn("days", t2.meta.get("missing", []))
        self.assertIn("transport", t2.meta.get("missing", []))
        self.assertIn("地铁", t2.reply)

        t3 = handle_user_message(t2.session, "自驾租车", llm=None, mode="ROUTE")
        self.assertEqual(t3.session.slots.transport_preferences, ["自驾"])
        self.assertIn("tags", t3.meta.get("missing", []))

        t4 = handle_user_message(t3.session, "我带着长辈", llm=None, mode="ROUTE")
        self.assertIn("带长辈出行", t4.session.slots.tags)
        self.assertEqual(t4.session.current_state, State.CONVERGENCE)
        self.assertIn("下一步", t4.reply)
        self.assertNotIn("为锚", t4.reply)
        self.assertNotIn("武隆", t4.reply)
        session = Session(
            current_state=State.RISK_CLARIFY,
            slots=Slots(
                destination="南京",
                days=3,
                anchor="玩",
                tags=["带长辈出行"],
                transport_preferences=["地铁", "步行"],
            ),
            has_conflict=True,
            conflict_detail={"reason": "test"},
        )
        turn = handle_user_message(session, "继续")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)

    def test_complete_slots_no_conflict(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(
            destination="南京",
            days=2,
            anchor="玩",
            tags=["年轻情侣/朋友"],
            transport_preferences=["地铁", "步行"],
        )
        turn = handle_user_message(session, "确认")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)
        self.assertFalse(turn.session.has_conflict)

    def test_unsupported_destination_blocks_convergence(self):
        session = Session()
        turn = handle_user_message(session, "想去上海玩3天", llm=None, mode="ROUTE")
        self.assertEqual(turn.session.current_state, State.SLOT_FILLING)
        self.assertEqual(turn.meta.get("action"), "unsupported_destination")
        self.assertIn("上海", turn.reply)
        self.assertIn("北京", turn.reply)
        self.assertIn("destination", turn.meta.get("missing", []))

        turn2 = handle_user_message(turn.session, "那改去南京", llm=None, mode="ROUTE")
        self.assertEqual(turn2.session.slots.destination, "南京")
        self.assertNotEqual(turn2.meta.get("action"), "unsupported_destination")

    def test_chengdu_is_supported_destination(self):
        session = Session()
        turn = handle_user_message(session, "成都4天", llm=None, mode="ROUTE")
        self.assertEqual(turn.session.slots.destination, "成都")
        self.assertNotEqual(turn.meta.get("action"), "unsupported_destination")

    def test_uncertain_days_applies_default(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(destination="重庆", anchor="玩")
        turn = handle_user_message(session, "天数不确定", llm=None, mode="ROUTE")
        self.assertEqual(turn.session.slots.days, 3)
        self.assertIn("3 天", turn.reply)
        self.assertNotIn("days", turn.meta.get("missing", []))

    def test_multi_slot_ack_on_first_message(self):
        turn = handle_user_message(
            Session(),
            "南京3天",
            llm=None,
            mode="ROUTE",
        )
        self.assertIn("好～", turn.reply)
        self.assertIn("南京", turn.reply)
        self.assertIn("3天", turn.reply)
        self.assertIn("地铁", turn.reply)

    def test_slot_progress_in_meta(self):
        session = Session()
        turn = handle_user_message(session, "想去南京", llm=None, mode="ROUTE")
        progress = turn.meta.get("slot_progress", {})
        self.assertTrue(progress.get("destination"))
        self.assertFalse(progress.get("days"))

    def test_transport_question_before_convergence(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(
            destination="重庆",
            days=3,
            anchor="玩",
            tags=["年轻情侣/朋友"],
        )
        turn = handle_user_message(session, "确认", llm=None, mode="ROUTE")
        self.assertEqual(turn.session.current_state, State.SLOT_FILLING)
        self.assertIn("transport", turn.meta.get("missing", []))
        self.assertIn("地铁", turn.reply)

        turn2 = handle_user_message(turn.session, "都可以，地铁步行就行", llm=None, mode="ROUTE")
        self.assertEqual(turn2.session.current_state, State.CONVERGENCE)
        self.assertEqual(turn2.session.transport_preferences, ["地铁", "步行"])
        self.assertIn("地铁加步行", turn2.reply)

    def test_chongqing_route_asks_transport_before_tags(self):
        msg = (
            "我已经订好了去重庆的机票，打算玩3天。听说那里的马路是立体迷宫。"
            "我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！"
        )
        turn = handle_user_message(Session(), msg, llm=None, mode="ROUTE")
        self.assertEqual(turn.session.slots.destination, "重庆")
        self.assertEqual(turn.session.slots.days, 3)
        self.assertEqual(turn.session.slots.transport_preferences, [])
        self.assertIn("transport", turn.meta.get("missing", []))
        self.assertIn("去重庆玩3天", turn.reply)
        self.assertIn("地铁", turn.reply)
        self.assertIn("自驾", turn.reply)
        self.assertNotIn("路上按", turn.reply)
        self.assertNotIn("和谁一起", turn.reply)

    def test_event_mode_auto_profile_skips_tags_question(self):
        msg = "出差到重庆，想抽半天随便走走，帮我安排个轻松的行程。"
        turn = handle_user_message(Session(), msg, llm=None, mode="EVENT")
        self.assertEqual(turn.session.slots.destination, "重庆")
        self.assertIn("商务出差", turn.session.slots.tags)
        self.assertNotIn("tags", turn.meta.get("missing", []) or [])
        self.assertNotIn("场合", turn.reply)
        self.assertNotIn("和谁一起", turn.reply)
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)

    def test_profile_vague_ack_uses_mode_default(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(
            destination="重庆",
            days=3,
            anchor="吃",
            transport_preferences=["地铁", "步行"],
        )
        turn = handle_user_message(session, "随便", llm=None, mode="FOOD")
        self.assertEqual(turn.session.slots.tags, ["年轻情侣/朋友"])
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)


if __name__ == "__main__":
    unittest.main()
