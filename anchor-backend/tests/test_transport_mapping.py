"""出行方式偏好解析测试。"""

import unittest

from anchor.transport_mapping import (
    describe_transport_preferences,
    extract_transport_preferences,
    transport_is_satisfied,
)


class TestTransportMapping(unittest.TestCase):
    def test_extract_metro_walk(self):
        prefs = extract_transport_preferences("地铁加步行就行")
        self.assertEqual(prefs, ["地铁", "步行"])

    def test_extract_drive(self):
        prefs = extract_transport_preferences("我想自驾租车")
        self.assertEqual(prefs, ["自驾"])

    def test_extract_flexible_default(self):
        prefs = extract_transport_preferences("都可以，看情况")
        self.assertEqual(prefs, ["地铁", "步行"])

    def test_describe_preferences(self):
        self.assertEqual(describe_transport_preferences(["地铁", "步行"]), "地铁加步行")
        self.assertEqual(describe_transport_preferences(["自驾"]), "自驾/租车")

    def test_transport_is_satisfied(self):
        self.assertFalse(transport_is_satisfied([]))
        self.assertTrue(transport_is_satisfied(["地铁", "步行"]))


if __name__ == "__main__":
    unittest.main()
