#!/usr/bin/env python3
"""Validate contest-required files and common credential leaks."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "CONTEST_DECLARATION.md",
    "MCP_INTEGRATION.md",
    "mcp-config.example.json",
    "workbuddy.md",
    "scripts/fries_planner.py",
    "scripts/mcp_client.py",
    "scripts/smoke_test.py",
    "scripts/make_share_card.py",
)
EXPECTED_DECLARATION = """# 参赛声明

## 原创性声明

参赛项目系原创开发，或已取得合法授权使用相关代码、组件、素材或其他内容，不侵犯任何第三方的知识产权、隐私权、商业秘密或其他合法权益。

## 合规声明

参赛项目及相关内容不存在违法犯罪、侵权、低俗、暴力、歧视、赌博等情形，不包含恶意代码、病毒、后门程序、钓鱼链接或其他可能危害网络安全的内容，亦不含有指向违规站点的外部链接。

## 信息安全声明

参赛项目及提交材料中不包含真实 Token、密钥、密码、账号凭证，亦不包含他人个人信息，配置文件仅使用环境变量占位符。

## 使用提示

参赛项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。

## 规则遵守声明

本人已仔细阅读并同意遵守《麦当劳程序员节创意开发大赛活动规则》，理解并接受其中关于参赛资格、项目要求、评审机制、奖品发放、个人信息处理及违规处理的相关规定。

如本人违反活动规则，或上述声明内容不真实，本人同意麦当劳有权在不事先通知的情况下取消本人的参赛资格、获奖资格及相关奖励；如因此给麦当劳造成损失的，本人同意依法承担相应责任。
"""
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "JWT bearer": re.compile(r"Bearer\s+eyJ[A-Za-z0-9_-]{20,}"),
    "long literal bearer": re.compile(r"Bearer\s+(?!\$\{MCD_MCP_TOKEN\}|<Token>|\[REDACTED\])[A-Za-z0-9_-]{32,}"),
}
FORBIDDEN_FILENAMES = {".env", "mcp-config.local.json", "secrets.json"}


def iter_project_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
            yield path


def validate() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"缺少必需文件：{relative}")

    declaration_path = ROOT / "CONTEST_DECLARATION.md"
    if declaration_path.is_file():
        declaration = declaration_path.read_text(encoding="utf-8")
        if declaration != EXPECTED_DECLARATION:
            errors.append("CONTEST_DECLARATION.md 与官方原文不一致")

    config_path = ROOT / "mcp-config.example.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            headers = config["mcpServers"]["mcd-mcp"]["headers"]
            if headers.get("Authorization") != "Bearer ${MCD_MCP_TOKEN}":
                errors.append("示例配置只能使用 MCD_MCP_TOKEN 环境变量占位符")
            if config["mcpServers"]["mcd-mcp"].get("url") != "https://mcp.mcd.cn":
                errors.append("示例配置的 MCP Server 地址不是官方地址")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"示例 MCP 配置无效：{exc}")

    skill_path = ROOT / "SKILL.md"
    if skill_path.is_file():
        skill = skill_path.read_text(encoding="utf-8")
        if not skill.startswith("---\n") or "name: fries-ensemble" not in skill:
            errors.append("SKILL.md frontmatter 或 name 无效")
        if "[TODO" in skill:
            errors.append("SKILL.md 仍包含初始化占位内容")

    for path in iter_project_files():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_FILENAMES or path.suffix == ".token":
            errors.append(f"仓库包含禁止的凭证文件：{relative}")
        if path.suffix.lower() not in {".md", ".py", ".json", ".html", ".gitignore", ".txt"} and path.name != ".gitignore":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path.suffix.lower() == ".html" and re.search(r"https?://", text, re.I):
            errors.append(f"{relative} 包含外部资源链接，分享卡应保持自包含")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative} 可能包含{label}")
        if re.search(r"[A-Z]:\\Users\\", text, re.I):
            errors.append(f"{relative} 包含本机用户目录")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print("错误：" + error, file=sys.stderr)
        return 1
    count = sum(1 for _ in iter_project_files())
    print(f"仓库校验通过：必需文件齐全，声明一致，未发现常见凭证泄露；共检查 {count} 个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
