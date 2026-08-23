import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("calculate_costs", ROOT / "scripts" / "calculate_costs.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SameWorkloadCostingTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples" / "same-workload-input.json").read_text(encoding="utf-8"))

    def test_expected_amounts_and_unchanged_hours(self):
        result = MODULE.calculate(self.data)["same_workload_costing"]
        self.assertEqual(result["workload_hours"], 1180.5)
        self.assertEqual(result["internal_cost_cny"], 126050.0)
        self.assertEqual(result["external_rebuild_cost_cny"], 185156.41)
        self.assertEqual(result["procurement_risk_reserve_cny"], 18515.64)
        self.assertEqual(result["procurement_budget_cny"], 203672.05)
        self.assertEqual(set(result["workload_amplification_factor"].values()), {1.0})
        self.assertEqual(result["tco"]["internal"]["total_cny"], 126050.0)
        self.assertEqual(result["tco"]["external_rebuild"]["total_cny"], 185156.41)
        self.assertEqual(result["tco"]["procurement_budget"]["total_cny"], 203672.05)

    def test_risk_rate_must_be_decimal(self):
        self.data["same_workload_costing"]["procurement_risk_rate"] = 10
        with self.assertRaisesRegex(ValueError, "0 到 1"):
            MODULE.calculate(self.data)

    def test_same_workload_mode_allows_empty_items(self):
        loaded = MODULE.load_input(ROOT / "examples" / "same-workload-input.json")
        self.assertEqual(loaded["items"], [])

    def test_recurring_items_are_added_to_matching_scenario_tco(self):
        self.data["items"] = [
            {
                "id": "OPS-INTERNAL",
                "name": "内部年度运行",
                "basis": "replacement",
                "category": "维护运营",
                "cost_nature": "recurring",
                "year": 2026,
                "end_year": 2030,
                "amount_cny": 100,
            },
            {
                "id": "OPS-PROCUREMENT",
                "name": "采购年度运行",
                "basis": "budget",
                "category": "维护运营",
                "cost_nature": "recurring",
                "year": 2026,
                "end_year": 2030,
                "amount_cny": 200,
            },
        ]
        result = MODULE.calculate(self.data)["same_workload_costing"]["tco"]
        self.assertEqual(result["internal"]["total_cny"], 126550.0)
        self.assertEqual(result["external_rebuild"]["total_cny"], 185656.41)
        self.assertEqual(result["procurement_budget"]["total_cny"], 204672.05)

    def test_duplicate_one_time_build_is_rejected(self):
        self.data["items"] = [{
            "id": "DUPLICATE-BUILD",
            "name": "重复建设",
            "basis": "budget",
            "category": "建设开发",
            "cost_nature": "one_time",
            "year": 2026,
            "amount_cny": 1,
        }]
        with self.assertRaisesRegex(ValueError, "不得再以 budget/replacement"):
            MODULE.calculate(self.data)

    def test_regular_items_use_half_up_money_rounding(self):
        data = {
            "meta": {
                "currency": "CNY",
                "start_year": 2026,
                "horizon_years": 1,
                "discount_rate": 0,
                "simulation_runs": 0,
            },
            "items": [{
                "id": "ROUNDING",
                "name": "舍入测试",
                "basis": "actual",
                "category": "测试",
                "cost_nature": "one_time",
                "year": 2026,
                "amount_cny": 2.675,
            }],
        }
        self.assertEqual(MODULE.calculate(data)["bases"]["actual"]["total_cny"], 2.68)

    def test_recurring_item_is_clipped_to_horizon(self):
        self.data["items"] = [{
            "id": "CROSS-PERIOD",
            "name": "跨期运行",
            "basis": "replacement",
            "category": "维护运营",
            "cost_nature": "recurring",
            "year": 2025,
            "end_year": 2027,
            "amount_cny": 100,
        }]
        result = MODULE.calculate(self.data)["same_workload_costing"]["tco"]["internal"]
        self.assertEqual(result["total_cny"], 126250.0)
        self.assertNotIn("2025", result["by_year"])

    def test_tco_total_equals_sum_of_displayed_years(self):
        self.data["items"] = [{
            "id": "GROWTH",
            "name": "增长运行费",
            "basis": "replacement",
            "category": "维护运营",
            "cost_nature": "recurring",
            "year": 2026,
            "end_year": 2030,
            "amount_cny": 100.01,
            "annual_growth_rate": 0.03,
        }]
        calculated = MODULE.calculate(self.data)
        regular = calculated["bases"]["replacement"]
        scenario = calculated["same_workload_costing"]["tco"]["internal"]
        self.assertEqual(regular["total_cny"], MODULE.money(sum(regular["by_year"].values())))
        self.assertEqual(regular["total_cny"], MODULE.money(sum(regular["by_category"].values())))
        self.assertEqual(regular["total_cny"], MODULE.money(sum(regular["by_evidence_grade"].values())))
        self.assertEqual(scenario["total_cny"], MODULE.money(sum(scenario["by_year"].values())))

    def test_simulation_uses_half_up_money_rounding(self):
        data = {
            "meta": {
                "currency": "CNY",
                "start_year": 2026,
                "horizon_years": 1,
                "discount_rate": 0,
                "simulation_runs": 2,
                "random_seed": 1,
            },
            "items": [{
                "id": "SIM-ROUNDING",
                "name": "模拟舍入测试",
                "basis": "actual",
                "category": "测试",
                "cost_nature": "one_time",
                "year": 2026,
                "amount_cny": 2.675,
                "uncertainty": {"low_factor": 1, "most_likely_factor": 1, "high_factor": 1},
            }],
        }
        simulation = MODULE.calculate(data)["simulation"]["actual"]
        self.assertEqual(set(simulation.values()), {2.68})


if __name__ == "__main__":
    unittest.main()
