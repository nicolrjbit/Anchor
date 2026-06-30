"""方案诊断与专家建议单元测试。"""

import unittest

from anchor.plan_advisor import expand_with_template, generate_plan_advice
from anchor.plan_diagnosis import (
    MustVisitPoi,
    PlanDayMetrics,
    PlanMetrics,
    diagnose_plan,
)


class TestPlanDiagnosis(unittest.TestCase):
    def _base_metrics(self, **kwargs) -> PlanMetrics:
        defaults = dict(
            destination="南京",
            days=3,
            anchor="中山陵",
            tags=["带长辈", "控制劳累度"],
            luggage_count=0,
            day_metrics=[
                PlanDayMetrics(
                    day_index=1,
                    matching_scores=[90, 88, 86],
                    must_visit_pois=[
                        MustVisitPoi("中山陵", 55),
                    ],
                    tran_cost=60,
                    attract_cost=40,
                    fatigue_index=100,
                )
            ],
        )
        defaults.update(kwargs)
        return PlanMetrics(**defaults)

    def test_pro_high_matching(self):
        d = diagnose_plan(self._base_metrics())
        keys = [p.rule_key for p in d.pros]
        self.assertIn("high_matching", keys)
        self.assertIn("no_luggage", keys)

    def test_con_heavy_tran_and_fatigue(self):
        d = diagnose_plan(self._base_metrics())
        keys = [c.rule_key for c in d.cons]
        self.assertIn("heavy_tran", keys)
        self.assertIn("fatigue_over", keys)
        self.assertIn("low_matching_must", keys)

    def test_con_frequent_hotel(self):
        m = self._base_metrics(luggage_count=2)
        d = diagnose_plan(m)
        self.assertTrue(any(c.rule_key == "frequent_hotel" for c in d.cons))

    def test_pro_hardcore_day(self):
        m = PlanMetrics(
            destination="南京",
            days=2,
            anchor="紫金山",
            tags=["特种兵"],
            day_metrics=[
                PlanDayMetrics(
                    day_index=1,
                    matching_scores=[88],
                    tran_cost=10,
                    attract_cost=50,
                    fatigue_index=60,
                )
            ],
        )
        d = diagnose_plan(m)
        self.assertTrue(any(p.rule_key == "hardcore_full" for p in d.pros))

    def test_template_advice_no_engineering_words(self):
        _, advice = generate_plan_advice(self._base_metrics())
        self.assertTrue(advice.startswith("-"))
        for word in ("算法", "JSON", "代码", "数据维度"):
            self.assertNotIn(word, advice)

    def test_expand_includes_tip(self):
        d = diagnose_plan(self._base_metrics())
        text = expand_with_template(d)
        # 触发的缺陷应带上可执行的避坑贴士
        self.assertTrue(any(kw in text for kw in ("换乘", "泡脚", "下午茶")))


if __name__ == "__main__":
    unittest.main()
