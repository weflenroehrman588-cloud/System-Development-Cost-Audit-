# 使用说明

## 1. 选择核算口径

开始计算前先确定用途：

| 口径 | 回答的问题 | 首选证据 |
|---|---|---|
| 实际发生成本 | 单位实际耗费了多少 | 财务凭证、工时、合同、发票、资产和账单 |
| 内部标准化经济成本 | 现有系统按内部 AI 辅助方式重建需要多少 | 逐文件工时、非文件活动和内部完全人工费率 |
| 同工时外部重建 | 同一工作量改用外部综合费率需要多少 | 内部核定工时、外部费率和直接费用 |
| 简化采购预算 | 外部重建金额加透明风险准备后是多少 | 外部重建金额和采购风险率 |
| 年度运行与 TCO | 建设后持续运行需要多少 | 服务器、存储、网络、电力、AI 和维护数据 |
| 分部分项详细报价 | 各模块、功能和人员分别投入多少、如何计价 | 建设要求、现有系统基线、WBS、人日、费率和验收标准 |

不同口径分别报告，不相加、不平均。

## 2. 逐文件估算内部工时

在项目根目录执行：

```bash
python3 /path/to/research-system-cost-evaluator/scripts/analyze_project_files.py \
  /path/to/project \
  --hourly-rate 100 \
  --format csv > /tmp/file-costs.csv
```

脚本会按文件类型、有效行、决策点、函数、接口、测试和风险标签估算有效工时。生成后必须人工复核高复杂度文件，并另行补充需求、联调验收、创新试验、沟通培训、部署和文档等非文件活动。

## 3. 配置同工时换价

复制 `examples/same-workload-input.json`，填写：

| 字段 | 含义 |
|---|---|
| `workload_hours` | 内部逐文件与非文件活动核定后的建设总工时 |
| `internal_hourly_rate_cny` | 内部完全小时成本 |
| `internal_direct_cost_cny` | 内部 AI 工具、测试环境等直接费用 |
| `person_month_hours` | 外部费率对应的有效人月工时 |
| `external_monthly_rate_cny` | 外部含税综合人月费率 |
| `external_direct_cost_cny` | 外部重建可识别直接费用 |
| `procurement_risk_rate` | 采购金额风险准备率，10%填写 `0.1` |
| `recurring_basis_mapping` | 三个同工时场景分别沿用哪一组年度运行明细 |

三种口径必须共用 `workload_hours`。若采购范围新增了驻场、等保整改、SLA 或质保，应把新增范围单独估算，不得暗中放大共同工时。

## 4. 复算

```bash
python3 scripts/calculate_costs.py input.json \
  --json-output result.json \
  --markdown-output result.md
```

输出的 `same_workload_costing` 包含：

- 共同工作小时和折算人月；
- 三种口径的工作量放大因子；
- 内部成本、外部重建、采购风险准备和采购预算；
- 可直接写入报告的公式说明。
- 三个场景自动注入建设金额后的年度 TCO 和折现现值。

输入中的 `items` 用于实际、预算或重建口径的成本明细。同工时模式会根据 `recurring_basis_mapping` 选取经常性明细并自动注入对应建设金额形成 TCO。为防止重复，同工时模式下不得再用 `budget` 或 `replacement` 明细录入一次性建设成本；仅需计算建设换价时，允许 `items` 为空数组。

## 5. 编制报告

- 普通全生命周期核算使用 `templates/cost-evaluation-report.md`；
- 内部专项评估使用 `templates/internal-cost-audit-report.md`；
- 输入结构从 `templates/cost-input-template.json` 复制；
- 证据等级、成本边界、计算方法和报告性质分别见 `references/`。

报告至少披露：对象、用途、期间、价格基准日、币种税费、范围、排除项、公式、关键参数、证据等级、分口径结果、TCO、防重复检查和待补资料。

## 6. 证据与结论限制

核心数据主要来自专家估计或公开市场信息时，应标记为初步估算。只有取得并核对工资福利、工时、合同、发票、资产台账、云账单和 AI 账单后，才可讨论实际发生成本。

正式采购前仍应在冻结范围下取得有效供应商报价；同工时外部重建和简化采购预算只是内部决策参考。

## 7. 生成分部分项工作量与报价方案

当用户提供建设要求、工程量清单模板，或要求同时统计模块、功能、人员和报价时，复制 `templates/detailed-quotation-input.json`：

- `current_system_baseline` 记录现有能力、证据、融合方式和是否重复计价；
- `modules[].items[]` 拆到可独立说明主要内容、验收标准和人日的最小计价项；
- `person_days` 把每个功能项的人日分到具体人员，其合计必须等于该项 `days`；
- `implementation_plan` 记录阶段、交付物、验收/付款条件；
- `exclusions` 明确硬件、商业软件、数据迁移、外部测评和维护等边界。

仅生成标准库支持的可复算成果：

```bash
python3 scripts/generate_detailed_quotation.py input.json \
  --output-dir output \
  --prefix 工作量统计与报价方案 \
  --formats json,csv,md
```

生成 Excel 和 A4 纵向 Word：

```bash
python3 -m pip install -r requirements-docs.txt
python3 scripts/generate_detailed_quotation.py input.json \
  --output-dir output \
  --prefix 工作量统计与报价方案 \
  --formats all
```

脚本会校验功能—人员、模块—人员、个人—项目三层人日及金额。详细结构、取整分摊和验收要求见 `references/detailed-workload-quotation.md`。
