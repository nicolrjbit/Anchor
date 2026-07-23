"""对话内容审核：重复追问检测。"""

import unittest

from anchor.dialogue_handler import handle_user_message
from anchor.dialogue_review import (
    detect_repeat_question,
    resolve_followup_focus,
    review_slot_followup,
    slot_filled_this_turn,
)
from anchor.prompts import compose_followup, build_multi_slot_ack
from anchor.slots import Slots
from anchor.state_machine import Session


class TestDialogueReview(unittest.TestCase):
    def test_slot_filled_this_turn_days(self):
        before = Slots(destination="南京")
        after = Slots(destination="南京", days=3)
        self.assertTrue(slot_filled_this_turn("days", before, after))
        self.assertFalse(slot_filled_this_turn("destination", before, after))

    def test_detect_repeat_question_same_text(self):
        reply = "这趟大概玩几天？"
        self.assertTrue(
            detect_repeat_question(
                reply,
                "days",
                last_asked_focus="days",
                last_reply="这趟大概玩几天？",
            )
        )

    def test_detect_repeat_question_different_focus(self):
        reply = "这趟大概玩几天？"
        self.assertFalse(
            detect_repeat_question(
                reply,
                "days",
                last_asked_focus="destination",
                last_reply="你想去哪个城市？",
            )
        )

    def test_resolve_skips_focus_when_user_just_filled(self):
        before = Slots(destination="南京")
        after = Slots(destination="南京", days=3)
        focus, missing, _ = resolve_followup_focus(
            ["days", "tags"],
            mode="ROUTE",
            before=before,
            after=after,
            last_asked_focus="days",
            message="3天",
        )
        self.assertNotEqual(focus, "days")
        self.assertNotIn("days", missing)

    def test_review_rephrases_identical_followup(self):
        session = Session()
        session.last_asked_focus = "days"
        session.last_assistant_reply = "这趟大概玩几天？"

        before = Slots(destination="南京")
        after = Slots(destination="南京")

        def build_question(focus, slots):
            return "这趟大概玩几天？"

        reply, focus, missing, slots, audit = review_slot_followup(
            session=session,
            missing=["days"],
            before=before,
            after=after,
            message="嗯",
            mode="ROUTE",
            extra_note=None,
            build_question=build_question,
            build_ack=build_multi_slot_ack,
            compose=compose_followup,
        )
        self.assertTrue(audit.get("repeat_detected"))
        self.assertTrue(audit.get("rephrased"))
        self.assertNotEqual(reply.strip(), session.last_assistant_reply.strip())

    def test_dialogue_no_repeat_days_question_after_answer(self):
        session = Session()
        t1 = handle_user_message(session, "想去南京", llm=None, mode="ROUTE")
        first_days_reply = t1.reply

        t2 = handle_user_message(t1.session, "3天", llm=None, mode="ROUTE")
        self.assertEqual(t2.session.slots.days, 3)
        if "几天" in first_days_reply:
            self.assertNotEqual(t2.reply.strip(), first_days_reply.strip())


if __name__ == "__main__":
    unittest.main()
