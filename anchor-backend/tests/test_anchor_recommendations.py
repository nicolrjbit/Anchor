import unittest

from anchor.anchor_recommendations import build_anchor_recommendations, suggest_anchor_recommendations
from anchor.dialogue_handler import handle_user_message
from anchor.slots import Slots
from anchor.state_machine import Session
from anchor.states import State


class TestAnchorRecommendations(unittest.TestCase):
    def test_play_anchor_includes_rating_and_visit_time(self):
        bundle = build_anchor_recommendations(
            Slots(destination="重庆", days=3, anchor="玩", tags=["年轻情侣/朋友"])
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle.anchor, "玩")
        self.assertGreaterEqual(len(bundle.picks), 3)
        pick = bundle.picks[0]
        self.assertEqual(pick.poi_type, "玩")
        self.assertGreater(pick.rating, 0)
        self.assertIn("小时", pick.visit_time)
        self.assertIn("简介", bundle.to_dict()["text"])
        self.assertNotIn("气质", pick.to_dict().get("intro", ""))
        self.assertTrue(pick.to_dict().get("intro"))

    def test_play_anchor_includes_sketch_image(self):
        bundle = build_anchor_recommendations(
            Slots(destination="重庆", days=3, anchor="玩", tags=["年轻情侣/朋友"])
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        pick = bundle.picks[0]
        data = pick.to_dict()
        self.assertIn("sketch_image", data)
        self.assertIn("/archor/images/sketches/", data["sketch_image"])

    def test_stay_anchor_recommends_hotels(self):
        text = suggest_anchor_recommendations(
            Slots(destination="重庆", days=5, anchor="住", tags=["商务出差"])
        )
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("第一锚点已锁定", text)
        self.assertIn("住", text)
        self.assertIn("酒店", text)
        self.assertIn("评分", text)

    def test_eat_anchor_recommends_restaurants(self):
        text = suggest_anchor_recommendations(
            Slots(destination="重庆", days=5, anchor="吃", tags=["年轻情侣/朋友"])
        )
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("餐厅", text)
        self.assertIn("珮姐", text)

    def test_convergence_computes_anchor_recs_without_showing_them(self):
        session = Session()
        session.current_state = State.SLOT_FILLING
        session.slots = Slots(
            destination="重庆",
            days=3,
            anchor="玩",
            tags=["亲子游出行"],
            transport_preferences=["地铁", "步行"],
        )
        turn = handle_user_message(session, "确认")
        self.assertEqual(turn.session.current_state, State.CONVERGENCE)
        self.assertIn("下一步", turn.reply)
        # 后台计算候选供 P3，但对话里不展示推荐详情
        self.assertTrue(turn.session.anchor_recommendations)
        self.assertNotIn("推荐理由", turn.reply)
        self.assertNotIn("第一锚点已锁定", turn.reply)


if __name__ == "__main__":
    unittest.main()
