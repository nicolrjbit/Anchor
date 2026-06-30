import unittest

from anchor.follow_recommendations import build_follow_recommendations
from anchor.state_machine import Session
from anchor.slots import Slots
from anchor.states import State


class TestFollowRecommendations(unittest.TestCase):
    def test_follow_for_play_anchor(self):
        session = Session(
            current_state=State.CONVERGENCE,
            slots=Slots(destination="重庆", days=3, anchor="玩", tags=["年轻情侣/朋友"]),
            travel_mode="play_drive",
            selected_anchor_pois=[
                {"poi_id": "cq_play_hongyadong", "name": "洪崖洞民俗风貌区", "poi_type": "玩"},
            ],
        )
        data = build_follow_recommendations(session.to_dict())
        self.assertEqual(data["follow_type"], "住")
        self.assertGreaterEqual(len(data["groups"]), 1)
        self.assertGreaterEqual(len(data["groups"][0]["picks"]), 1)


if __name__ == "__main__":
    unittest.main()
