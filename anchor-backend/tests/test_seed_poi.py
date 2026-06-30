"""POI 种子数据测试。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from anchor.poi_repository import get_attractions_by_city, get_route_chains, poi_counts
from db.init_db import init_db


class TestSeedPoi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        init_db(self.db_path)

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_poi_counts(self):
        counts = poi_counts(self.db_path)
        self.assertEqual(counts["attractions"], 96)
        self.assertEqual(counts["hotels"], 60)
        self.assertEqual(counts["restaurants"], 71)
        self.assertGreaterEqual(counts["traffic_segment"], 20)

    def test_ten_hotels_per_city(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT city, COUNT(*) FROM hotels GROUP BY city ORDER BY city"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 6)
        for city, count in rows:
            self.assertEqual(count, 10, city)

    def test_four_cities_attractions(self):
        for city in ("北京", "南京", "重庆", "新疆", "成都", "西安"):
            rows = get_attractions_by_city(city, db_path=self.db_path, limit=20)
            self.assertGreaterEqual(len(rows), 12, city)
            tiers = {r.attract_tier for r in rows}
            self.assertTrue(tiers & {"特级", "高级", "中级", "低级"})
            for row in rows:
                self.assertTrue(row.brief_intro, f"{row.id} 缺少 brief_intro")

    def test_route_chains_from_db(self):
        chains = get_route_chains("重庆", db_path=self.db_path)
        self.assertGreaterEqual(len(chains), 2)
        self.assertIn("→", chains[0])

    def test_matching_tag_table(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT matching_tag FROM map_user_tag_matching WHERE user_tag=? AND attract_tier=?",
            ("带长辈出行", "中级"),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], 1.1)


if __name__ == "__main__":
    unittest.main()
