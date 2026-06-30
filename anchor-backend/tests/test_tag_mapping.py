"""用户画像标签解析测试。"""

import unittest

from anchor.slots import Slots
from anchor.tag_mapping import (
    has_profile_tag,
    infer_profile_tags,
    resolve_profile_tags,
    sanitize_profile_tags,
)


class TestTagMapping(unittest.TestCase):
    def test_infer_profile_tags(self):
        self.assertIn(
            "大学生/年轻毕业生",
            infer_profile_tags("我和大学同学一起去"),
        )
        self.assertIn(
            "带长辈出行",
            infer_profile_tags("带爸妈一起，不要太累"),
        )
        self.assertIn(
            "商务出差",
            infer_profile_tags("出差顺路玩半天"),
        )

    def test_synonym_counts_as_profile(self):
        self.assertFalse(has_profile_tag(["带长辈"]))
        self.assertTrue(has_profile_tag(["带长辈出行"]))
        self.assertEqual(
            resolve_profile_tags(["带长辈", "亲子游家庭"]),
            ["带长辈出行", "亲子游出行"],
        )

    def test_preference_words_not_tags(self):
        self.assertFalse(has_profile_tag(["美食寻味"]))
        self.assertFalse(has_profile_tag(["景点打卡"]))
        self.assertEqual(sanitize_profile_tags(["美食寻味", "年轻情侣/朋友"]), ["年轻情侣/朋友"])
        self.assertEqual(resolve_profile_tags(["特种兵", "美食寻味"]), [])

    def test_zhefan_not_a_tag(self):
        from anchor.nlu import extract_slots

        slots = extract_slots(
            "我已经订好了去重庆的机票，听说那里的马路是立体迷宫。"
            "我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！",
            Slots(),
            llm=None,
            mode="ROUTE",
        )
        self.assertEqual(slots.tags, [])
        self.assertNotIn("景点打卡", slots.tags)
        self.assertEqual(slots.anchor, "玩")


if __name__ == "__main__":
    unittest.main()
