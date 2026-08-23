#!/usr/bin/env python3
"""科研信息系统成本复算器。仅使用 Python 标准库。"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import mean
from typing import Any


VALID_BASES = {"actual", "budget", "replacement"}
VALID_NATURES = {"one_time", "recurring"}
SAME_WORKLOAD_SCENARIOS = {
    "internal": "internal_cost_cny",
    "external_rebuild": "external_rebuild_cost_cny",
    "procurement_budget": "procurement_budget_cny",
}


def money(value: float | Decimal) -> float:
    """人民币金额按四舍五入到分输出，避免二进制浮点和银行家舍入差异。"""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_same_workload(data: dict[str, Any]) -> dict[str, Any] | None:
    """按内部核定工时计算内部、外部重建和简化采购三个可比口径。"""
    config = data.get("same_workload_costing")
    if not config or not config.get("enabled", False):
        return None

    required = (
        "workload_hours",
        "internal_hourly_rate_cny",
        "internal_direct_cost_cny",
        "person_month_hours",
        "external_monthly_rate_cny",
        "external_direct_cost_cny",
        "procurement_risk_rate",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"same_workload_costing 缺少字段: {missing}")

    workload = Decimal(str(config["workload_hours"]))
    internal_rate = Decimal(str(config["internal_hourly_rate_cny"]))
    internal_direct = Decimal(str(config["internal_direct_cost_cny"]))
    month_hours = Decimal(str(config["person_month_hours"]))
    external_monthly_rate = Decimal(str(config["external_monthly_rate_cny"]))
    external_direct = Decimal(str(config["external_direct_cost_cny"]))
    risk_rate = Decimal(str(config["procurement_risk_rate"]))

    if workload <= 0 or month_hours <= 0:
        raise ValueError("same_workload_costing 的 workload_hours 和 person_month_hours 必须大于 0")
    if min(internal_rate, internal_direct, external_monthly_rate, external_direct, risk_rate) < 0:
        raise ValueError("same_workload_costing 的费率、直接费用和风险率不得为负数")
    if risk_rate > 1:
        raise ValueError("same_workload_costing 的 procurement_risk_rate 应使用 0 到 1 的小数")

    conflicting = [
        item["id"]
        for item in data.get("items", [])
        if item.get("cost_nature") == "one_time" and item.get("basis") in {"budget", "replacement"}
    ]
    if conflicting:
        raise ValueError(
            "启用 same_workload_costing 后，不得再以 budget/replacement items 重复录入一次性建设成本: "
            + ", ".join(conflicting)
        )

    internal_cost = Decimal(str(money(workload * internal_rate + internal_direct)))
    external_cost = Decimal(str(money(workload / month_hours * external_monthly_rate + external_direct)))
    risk_reserve = Decimal(str(money(external_cost * risk_rate)))
    procurement_budget = Decimal(str(money(external_cost + risk_reserve)))

    return {
        "scope_note": config.get("scope_note", "三种口径采用相同工作范围和内部核定工时"),
        "workload_hours": float(workload),
        "person_months": money(workload / month_hours),
        "workload_amplification_factor": {
            "internal": 1.0,
            "external_rebuild": 1.0,
            "procurement_budget": 1.0,
        },
        "function_points_usage": "仅用于功能范围完整性复核，不参与工时或金额计算",
        "internal_cost_cny": float(internal_cost),
        "external_rebuild_cost_cny": float(external_cost),
        "procurement_risk_reserve_cny": float(risk_reserve),
        "procurement_budget_cny": float(procurement_budget),
        "formula": {
            "internal": "Round2(H × internal_hourly_rate + internal_direct_cost)",
            "external_rebuild": "Round2(H ÷ person_month_hours × external_monthly_rate + external_direct_cost)",
            "procurement_risk": "Round2(external_rebuild_cost × procurement_risk_rate)",
            "procurement_budget": "Round2(external_rebuild_cost + procurement_risk_reserve)",
        },
    }


def load_input(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    meta = data.get("meta", {})
    if meta.get("currency") != "CNY":
        raise ValueError("currency 必须为 CNY；外币请先按有来源的汇率换算")
    same_workload_enabled = bool(data.get("same_workload_costing", {}).get("enabled", False))
    if not data.get("items") and not same_workload_enabled:
        raise ValueError("items 不能为空；仅计算同工时换价时需启用 same_workload_costing")
    return data


def validate_item(item: dict[str, Any]) -> None:
    missing = [key for key in ("id", "name", "basis", "category", "cost_nature", "year") if key not in item]
    if missing:
        raise ValueError(f"明细缺少字段 {missing}: {item}")
    if item["basis"] not in VALID_BASES:
        raise ValueError(f"{item['id']} 的 basis 无效")
    if item["cost_nature"] not in VALID_NATURES:
        raise ValueError(f"{item['id']} 的 cost_nature 无效")
    if "amount_cny" not in item and not {"quantity", "unit_price_cny"}.issubset(item):
        raise ValueError(f"{item['id']} 需要 amount_cny 或 quantity × unit_price_cny")
    rate = float(item.get("allocation_rate", 1.0))
    if rate < 0 or rate > 1:
        raise ValueError(f"{item['id']} 的 allocation_rate 必须在 0 到 1 之间")


def base_amount(item: dict[str, Any]) -> Decimal:
    if "amount_cny" in item:
        amount = Decimal(str(item["amount_cny"]))
    else:
        amount = Decimal(str(item.get("quantity", 0))) * Decimal(str(item.get("unit_price_cny", 0)))
    return amount * Decimal(str(item.get("allocation_rate", 1.0)))


def annual_amount(item: dict[str, Any], year: int) -> Decimal:
    initial_year = int(item["year"])
    growth = Decimal(str(item.get("annual_growth_rate", 0.0)))
    return base_amount(item) * ((1 + growth) ** (year - initial_year))


def expanded_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    meta = data["meta"]
    horizon_start = int(meta["start_year"])
    horizon_end = horizon_start + int(meta.get("horizon_years", 1)) - 1
    rows: list[dict[str, Any]] = []
    for item in data["items"]:
        validate_item(item)
        item_start = int(item["year"])
        if item["cost_nature"] == "one_time":
            if item_start < horizon_start or item_start > horizon_end:
                continue
            start = end = item_start
        else:
            start = max(item_start, horizon_start)
            end = min(int(item.get("end_year", horizon_end)), horizon_end)
            if end < start:
                continue
        for year in range(start, end + 1):
            row = dict(item)
            row["year"] = year
            row["amount_cny"] = Decimal(str(money(annual_amount(item, year))))
            rows.append(row)
    return rows


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def simulate(data: dict[str, Any]) -> dict[str, dict[str, float]]:
    meta = data["meta"]
    runs = int(meta.get("simulation_runs", 0))
    if runs <= 0:
        return {}
    randomizer = random.Random(int(meta.get("random_seed", 0)))
    totals = {basis: [] for basis in VALID_BASES}
    rows = expanded_rows(data)
    for _ in range(runs):
        run_total = defaultdict(float)
        sampled_factors: dict[str, float] = {}
        for row in rows:
            item_id = row["id"]
            uncertainty = row.get("uncertainty", {})
            if item_id not in sampled_factors:
                low = float(uncertainty.get("low_factor", 1.0))
                mode = float(uncertainty.get("most_likely_factor", 1.0))
                high = float(uncertainty.get("high_factor", 1.0))
                if not low <= mode <= high:
                    raise ValueError(f"{item_id} 的不确定性因子必须满足 low <= most_likely <= high")
                sampled_factors[item_id] = randomizer.triangular(low, high, mode)
            run_total[row["basis"]] += float(row["amount_cny"]) * sampled_factors[item_id]
        for basis in VALID_BASES:
            totals[basis].append(run_total[basis])
    return {
        basis: {
            "p10": money(percentile(values, 0.10)),
            "p50": money(percentile(values, 0.50)),
            "p90": money(percentile(values, 0.90)),
            "mean": money(mean(values)),
        }
        for basis, values in totals.items()
        if any(values)
    }


def calculate(data: dict[str, Any]) -> dict[str, Any]:
    meta = data["meta"]
    discount_rate = Decimal(str(meta.get("discount_rate", 0.0)))
    start_year = int(meta["start_year"])
    by_basis_category: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    by_basis_year: dict[str, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    evidence_by_basis: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in expanded_rows(data):
        basis = row["basis"]
        amount = row["amount_cny"]
        by_basis_category[basis][row["category"]] += amount
        by_basis_year[basis][row["year"]] += amount
        evidence_by_basis[basis][row.get("evidence_grade", "未标注")] += amount
    result: dict[str, Any] = {"meta": meta, "bases": {}, "simulation": simulate(data)}
    same_workload = calculate_same_workload(data)
    if same_workload is not None:
        recurring_mapping = data["same_workload_costing"].get("recurring_basis_mapping", {
            "internal": "replacement",
            "external_rebuild": "replacement",
            "procurement_budget": "budget",
        })
        if set(recurring_mapping) != set(SAME_WORKLOAD_SCENARIOS):
            raise ValueError("recurring_basis_mapping 必须完整包含 internal、external_rebuild、procurement_budget")
        if any(basis not in VALID_BASES for basis in recurring_mapping.values()):
            raise ValueError("recurring_basis_mapping 只能引用 actual、budget 或 replacement")
        horizon_end = start_year + int(meta.get("horizon_years", 1)) - 1
        scenario_tco: dict[str, Any] = {}
        rows = expanded_rows(data)
        for scenario, amount_key in SAME_WORKLOAD_SCENARIOS.items():
            construction = Decimal(str(same_workload[amount_key]))
            mapped_basis = recurring_mapping[scenario]
            yearly: dict[int, Decimal] = {year: Decimal("0") for year in range(start_year, horizon_end + 1)}
            yearly[start_year] += construction
            for row in rows:
                if row["cost_nature"] == "recurring" and row["basis"] == mapped_basis:
                    yearly[row["year"]] += row["amount_cny"]
            rounded_yearly = {
                year: Decimal(str(money(amount)))
                for year, amount in yearly.items()
            }
            npv = sum(
                amount / ((Decimal("1") + discount_rate) ** (year - start_year))
                for year, amount in rounded_yearly.items()
            )
            scenario_tco[scenario] = {
                "construction_cost_cny": money(construction),
                "recurring_basis": mapped_basis,
                "total_cny": money(sum(rounded_yearly.values(), Decimal("0"))),
                "npv_cny": money(npv),
                "by_year": {str(year): float(amount) for year, amount in rounded_yearly.items()},
            }
        same_workload["tco"] = scenario_tco
        result["same_workload_costing"] = same_workload
    for basis in sorted(by_basis_year):
        yearly = by_basis_year[basis]
        rounded_yearly = {
            year: Decimal(str(money(amount)))
            for year, amount in yearly.items()
        }
        npv = sum(
            amount / ((Decimal("1") + discount_rate) ** max(0, year - start_year))
            for year, amount in rounded_yearly.items()
        )
        result["bases"][basis] = {
            "total_cny": money(sum(rounded_yearly.values(), Decimal("0"))),
            "npv_cny": money(npv),
            "by_category": {key: money(value) for key, value in sorted(by_basis_category[basis].items())},
            "by_year": {str(key): float(value) for key, value in sorted(rounded_yearly.items())},
            "by_evidence_grade": {key: money(value) for key, value in sorted(evidence_by_basis[basis].items())},
        }
    return result


def markdown(result: dict[str, Any]) -> str:
    lines = ["# 成本计算结果", "", f"价格基准日：{result['meta'].get('price_base_date', '未填写')}", ""]
    same_workload = result.get("same_workload_costing")
    if same_workload:
        factors = same_workload["workload_amplification_factor"]
        lines.extend([
            "## 同工时换价", "",
            f"共同建设工作量：{same_workload['workload_hours']:,.1f} 小时", "",
            "| 口径 | 工作量（小时） | 放大因子 | 金额（元） |", "|---|---:|---:|---:|",
            f"| 内部标准化经济成本 | {same_workload['workload_hours']:,.1f} | {factors['internal']:.2f} | {same_workload['internal_cost_cny']:,.2f} |",
            f"| 同工时外部重建 | {same_workload['workload_hours']:,.1f} | {factors['external_rebuild']:.2f} | {same_workload['external_rebuild_cost_cny']:,.2f} |",
            f"| 简化采购建设预算 | {same_workload['workload_hours']:,.1f} | {factors['procurement_budget']:.2f} | {same_workload['procurement_budget_cny']:,.2f} |",
            "",
            f"采购金额风险准备：¥{same_workload['procurement_risk_reserve_cny']:,.2f}", "",
            f"功能点用途：{same_workload['function_points_usage']}", "",
            "| 同工时场景 | 建设成本（元） | 五年或设定期间TCO（元） | 折现现值（元） |", "|---|---:|---:|---:|",
            f"| 内部 | {same_workload['tco']['internal']['construction_cost_cny']:,.2f} | {same_workload['tco']['internal']['total_cny']:,.2f} | {same_workload['tco']['internal']['npv_cny']:,.2f} |",
            f"| 外部重建 | {same_workload['tco']['external_rebuild']['construction_cost_cny']:,.2f} | {same_workload['tco']['external_rebuild']['total_cny']:,.2f} | {same_workload['tco']['external_rebuild']['npv_cny']:,.2f} |",
            f"| 简化采购 | {same_workload['tco']['procurement_budget']['construction_cost_cny']:,.2f} | {same_workload['tco']['procurement_budget']['total_cny']:,.2f} | {same_workload['tco']['procurement_budget']['npv_cny']:,.2f} |",
            "",
        ])
    for basis, values in result["bases"].items():
        lines.extend([
            f"## {basis}", "",
            f"总成本：¥{values['total_cny']:,.2f}", "",
            f"折现现值：¥{values['npv_cny']:,.2f}", "",
            "| 年度 | 成本（元） |", "|---:|---:|",
        ])
        lines.extend(f"| {year} | {amount:,.2f} |" for year, amount in values["by_year"].items())
        simulation = result.get("simulation", {}).get(basis)
        if simulation:
            lines.extend(["", f"模拟区间：P10 ¥{simulation['p10']:,.2f}；P50 ¥{simulation['p50']:,.2f}；P90 ¥{simulation['p90']:,.2f}"])
        lines.append("")
    lines.append("不同 basis 为不同核算口径，禁止相加。模拟采用独立三角分布，未表达参数相关性。")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="科研信息系统人民币成本复算器")
    parser.add_argument("input", type=Path, help="输入 JSON")
    parser.add_argument("--json-output", type=Path, help="写出 JSON 结果")
    parser.add_argument("--markdown-output", type=Path, help="写出 Markdown 摘要")
    args = parser.parse_args()
    result = calculate(load_input(args.input))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.write_text(encoded + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.write_text(markdown(result), encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(encoded)


if __name__ == "__main__":
    main()
