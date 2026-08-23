#!/usr/bin/env python3
"""逐文件估算成熟框架下的 AI 辅助重建工时，结果用于成本讨论而非财务入账。"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


SOURCE_PATTERNS = (
    "frontend/src/**/*.vue",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.css",
    "frontend/index.html",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/tsconfig*.json",
    "frontend/.env.development",
    "frontend/.env.production",
    "backend/app/**/*.py",
    "backend/tests/**/*.py",
    "backend/scripts/**/*.py",
    "backend/init_data.py",
    "backend/requirements.txt",
    "backend/.env.example",
    "ecosystem.config.js",
    "start.sh",
    "stop.sh",
    "nginx.conf.example",
    "deploy/*.conf",
    "Product-Spec.md",
    "Product-Spec-CHANGELOG.md",
    "Design-Brief.md",
    "DEV-PLAN.md",
    "README.md",
)

EXCLUDED_PARTS = {"node_modules", "dist", ".venv", "__pycache__", ".pytest_cache"}

ROLE_RULES = (
    (r"^frontend/src/views/", "前端页面"),
    (r"^frontend/src/layouts/", "前端布局"),
    (r"^frontend/src/(api|router|stores|utils)/", "前端基础能力"),
    (r"^frontend/src/", "前端公共代码"),
    (r"^frontend/", "前端工程配置"),
    (r"^backend/app/api/", "后端API"),
    (r"^backend/app/services/", "后端服务"),
    (r"^backend/app/core/", "后端安全与基础能力"),
    (r"^backend/app/models/", "数据库模型"),
    (r"^backend/app/schemas/", "数据契约"),
    (r"^backend/app/db/", "数据库基础能力"),
    (r"^backend/tests/", "自动化测试"),
    (r"^backend/scripts/|^backend/init_data.py", "迁移与初始化"),
    (r"^backend/", "后端工程配置"),
    (r"^(deploy/|ecosystem|start\.sh|stop\.sh|nginx)", "部署配置"),
    (r"\.md$", "需求与交付文档"),
)

RISK_PATTERNS = {
    "认证安全": r"auth|jwt|token|password|bcrypt|captcha|login_guard|security",
    "外部接口": r"httpx|requests|OpenAI|deepseek|scrap|BeautifulSoup|external",
    "数据一致性": r"commit\(|rollback\(|Session|migration|migrate|bulk|transaction",
    "文件与PDF": r"upload|FileResponse|xhtml2pdf|pdf|openpyxl",
    "调度运行": r"scheduler|APScheduler|cron|pm2|nginx|systemctl",
}


def discover(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(
        path for path in files
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts)
    )


def role_for(relative: str) -> str:
    for pattern, role in ROLE_RULES:
        if re.search(pattern, relative):
            return role
    return "其他源码"


def strip_comments(lines: Iterable[str], suffix: str) -> list[str]:
    output: list[str] = []
    in_block = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if in_block:
            if "*/" in line or "-->" in line:
                in_block = False
            continue
        if line.startswith(("/*", "<!--")):
            if not ("*/" in line or "-->" in line):
                in_block = True
            continue
        if suffix in {".py", ".sh"} and line.startswith("#"):
            continue
        if suffix in {".ts", ".js", ".vue", ".css"} and line.startswith("//"):
            continue
        output.append(line)
    return output


def productivity(relative: str, role: str) -> float:
    if role in {"前端页面", "前端布局"}:
        return 30.0
    if role in {"前端基础能力", "前端公共代码"}:
        return 42.0
    if role == "前端工程配置":
        return 70.0
    if role in {"后端API", "后端服务"}:
        return 30.0
    if role == "后端安全与基础能力":
        return 36.0
    if role in {"数据库模型", "数据契约"}:
        return 58.0
    if role == "数据库基础能力":
        return 45.0
    if role == "自动化测试":
        return 48.0
    if role == "迁移与初始化":
        return 40.0
    if role in {"后端工程配置", "部署配置"}:
        return 55.0
    if role == "需求与交付文档":
        return 35.0
    return 45.0


def evaluate(path: Path, root: Path, hourly_rate: float) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    raw_lines = text.splitlines()
    code_lines = strip_comments(raw_lines, path.suffix.lower())
    code = "\n".join(code_lines)
    role = role_for(relative)
    decisions = len(re.findall(
        r"\b(?:if|elif|else|for|while|try|except|match|case)\b|\bv-(?:if|else-if|for)\b|&&|\|\|",
        code,
    ))
    functions = len(re.findall(
        r"^\s*(?:async\s+)?def\s+|\bfunction\s+\w+|\b(?:const|let)\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
        text,
        flags=re.MULTILINE,
    ))
    classes = len(re.findall(r"^\s*class\s+\w+", text, flags=re.MULTILINE))
    endpoints = len(re.findall(r"^\s*@(?:router|app)\.(?:get|post|put|patch|delete)", text, flags=re.MULTILINE))
    tests = len(re.findall(r"^\s*def\s+test_", text, flags=re.MULTILINE))
    risks = [name for name, pattern in RISK_PATTERNS.items() if re.search(pattern, relative + "\n" + code, re.I)]

    base = 0.15 if path.name == "__init__.py" else 0.6 if role.endswith("配置") else 1.0
    complexity_multiplier = 1 + min(decisions, 120) * 0.004 + min(functions + classes + endpoints + tests, 80) * 0.003
    risk_multiplier = 1 + min(len(risks), 3) * 0.08
    if relative.endswith("scraper.py") or relative.endswith("admin.py"):
        risk_multiplier += 0.10
    hours = base + len(code_lines) / productivity(relative, role) * complexity_multiplier * risk_multiplier
    hours = round(max(0.1, hours), 1)

    score = decisions + functions * 2 + classes * 2 + endpoints * 3 + tests + len(risks) * 4
    if score >= 70 or hours >= 55:
        grade = "关键"
    elif score >= 30 or hours >= 25:
        grade = "高"
    elif score >= 10 or hours >= 8:
        grade = "中"
    else:
        grade = "低"

    return {
        "path": relative,
        "role": role,
        "gross_lines": len(raw_lines),
        "effective_lines": len(code_lines),
        "decisions": decisions,
        "functions": functions,
        "endpoints_or_tests": endpoints + tests,
        "risks": "、".join(risks) if risks else "-",
        "complexity": grade,
        "hours": hours,
        "cost_cny": round(hours * hourly_rate, 2),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, float]] = defaultdict(lambda: {"files": 0, "effective_lines": 0, "hours": 0, "cost_cny": 0})
    for row in rows:
        group = groups[row["role"]]
        group["files"] += 1
        group["effective_lines"] += row["effective_lines"]
        group["hours"] += row["hours"]
        group["cost_cny"] += row["cost_cny"]
    return {
        "files": len(rows),
        "effective_lines": sum(row["effective_lines"] for row in rows),
        "hours": round(sum(row["hours"] for row in rows), 1),
        "cost_cny": round(sum(row["cost_cny"] for row in rows), 2),
        "by_role": {role: {key: round(value, 2) for key, value in values.items()} for role, values in sorted(groups.items())},
    }


def csv_text(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="逐文件AI辅助重建工时估算")
    parser.add_argument("root", type=Path)
    parser.add_argument("--hourly-rate", type=float, default=100.0)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args()
    root = args.root.resolve()
    rows = [evaluate(path, root, args.hourly_rate) for path in discover(root)]
    if not rows:
        raise SystemExit("未找到待分析文件")
    if args.format == "csv":
        print(csv_text(rows), end="")
    else:
        print(json.dumps({"summary": summarize(rows), "files": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
