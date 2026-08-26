# 科研事业单位信息系统成本核算 Skill

面向国内科研事业单位，以人民币核算信息系统的内部经济成本、实际发生成本、市场重建、预算参考、服务器与 AI 使用、维护及全生命周期成本。

本 Skill 的核心不是给出一个看似精确的“大总数”，而是把不同核算口径分开，并让每个金额能够追溯到工时、费率、直接费用、证据和公式。

## 主要能力

- 按前端、后端、测试、部署和文档逐文件分析 AI 辅助有效工时；
- 分开呈现实际发生成本、内部标准化经济成本、市场重建和采购预算；
- 核算服务器、存储、网络、电力、AI 及年度维护成本；
- 输出一年、三年和五年 TCO，可选折现现值；
- 生成适合内部管理复核的成本专项评估报告；
- 支持“全部采用内部工作小时”的同工时换价模式。
- 按“系统—模块—功能项”生成分部分项工作量清单与报价；
- 融合现有系统基线与新增功能，统计人员职责、模块—人员矩阵和个人工作量；
- 生成可复算 JSON/CSV/Markdown，以及紧凑的 A4 纵向 Excel/Word 成果。

## 同工时换价原则

当内部、外部重建和简化采购采用同一工作范围时，三种口径共用内部核定工时 `H`，工作量放大因子均为 `1.00`：

```text
内部成本 = Round2(H × 内部小时费率 + 内部直接费用)
外部重建 = Round2(H ÷ 人月工时 × 外部人月费率 + 外部直接费用)
风险准备 = Round2(外部重建 × 采购风险率)
采购预算 = Round2(外部重建 + 风险准备)
```

功能点仅用于检查功能范围，不参与工时或金额计算。采购风险只调整金额，不反推为新增工时。

## 目录

```text
research-system-cost-evaluator/
├── SKILL.md
├── README.md
├── USAGE.md
├── references/
├── scripts/
├── templates/
├── examples/
└── tests/
```

## 安装

克隆到 Codex 的技能目录：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/weflenroehrman588-cloud/System-Development-Cost-Audit-.git \
  ~/.codex/skills/research-system-cost-evaluator
```

重新启动会话后，可直接提出“评估这个科研信息系统的开发、服务器、AI、维护和五年 TCO”等请求，Codex 会按 `SKILL.md` 的触发条件使用本 Skill。

更新已有安装：

```bash
git -C ~/.codex/skills/research-system-cost-evaluator pull --ff-only
```

## 快速开始

```bash
python3 scripts/calculate_costs.py \
  examples/same-workload-input.json \
  --json-output /tmp/cost-result.json \
  --markdown-output /tmp/cost-result.md
```

预期的同工时换价结果：内部成本 `126,050.00` 元、外部重建 `185,156.41` 元、采购风险准备 `18,515.64` 元、简化采购预算 `203,672.05` 元。

完整示例输出见 [examples/same-workload-output.md](examples/same-workload-output.md)。

详细输入、逐文件分析、报告生成和证据要求见 [USAGE.md](USAGE.md)。

分部分项详细报价示例：

```bash
python3 -m pip install -r requirements-docs.txt
python3 scripts/generate_detailed_quotation.py \
  templates/detailed-quotation-input.json \
  --output-dir /tmp/detailed-quotation \
  --formats all
```

该模式会拒绝功能人日与人员分配不一致的输入，并输出模块汇总、功能明细、现有系统基线、人员统计、模块人员矩阵及实施计划。

## 适用边界

- 没有工资、工时、合同、发票、资产台账或账单时，只能输出内部经济成本或预算估算，不能称为实际财务成本。
- 本 Skill 生成的是内部管理支持材料，不替代注册会计师审计、国家审计或有资质机构的软件造价评估。
- 不同核算口径不得相加或取平均形成“综合成本”。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```
