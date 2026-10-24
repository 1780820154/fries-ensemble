#!/usr/bin/env python3
"""Build a fries order plan from live query-meals JSON without network access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

NAME_KEYS = ("mealName", "productName", "itemName", "skuName", "displayName", "name", "title")
CODE_KEYS = ("mealCode", "productCode", "itemCode", "skuCode", "code", "id")
STRONG_CODE_KEYS = ("mealCode", "productCode", "itemCode", "skuCode")
PRICE_KEYS = ("price", "salePrice", "currentPrice", "mealPrice", "sellPrice", "amount")
FRIES_RE = re.compile(r"薯条|脆薯|摇摇薯|(?:大|中|小)薯(?!饼)")
EXCLUDE_RE = re.compile(
    r"套餐|汉堡|薯饼|麦乐鸡|鸡腿|鸡翅|鸡肉|猪柳|牛肉|鱼肉|鱼柳|卷|饭|"
    r"儿童|乐园|可乐|雪碧|咖啡|奶茶|新地|冰激凌|冰淇淋|玉米|苹果|沙拉|"
    r"油条|粥|豆浆|牛奶|派|蛋|早餐"
)
FLAVOR_RE = re.compile(r"摇摇|风味|海苔|紫菜|芝士|奶酪|辣味|香辣|烧烤|番茄|松露|蒜香|芥末")
SIZE_RE = {
    "small": re.compile(r"小薯|小份|薯条[（(]?小|\bsmall\b", re.I),
    "medium": re.compile(r"中薯|中份|薯条[（(]?中|\bmedium\b", re.I),
    "large": re.compile(r"大薯|大份|薯条[（(]?大|\blarge\b", re.I),
}
CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
PRESETS = {"solo": (1, "medium"), "duet": (2, "medium"), "share": (4, "medium")}


class PlannerError(ValueError):
    """Raised for invalid planner input."""


@dataclass(frozen=True)
class OrderRequest:
    quantity: int = 1
    size: str = "medium"
    keyword: str | None = None
    preset: str = "custom"


@dataclass(frozen=True)
class FriesProduct:
    code: str
    name: str
    size: str
    flavor: str
    menu_price_raw: str | int | float | None = None


def first_value(data: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def is_unavailable(data: dict[str, Any]) -> bool:
    if data.get("available") is False or data.get("sellable") is False:
        return True
    if data.get("soldOut") is True or data.get("isSoldOut") is True:
        return True
    if data.get("stock") == 0 or data.get("inventory") == 0:
        return True
    status = str(data.get("status", "")).lower()
    return status in {"off", "inactive", "soldout", "sold_out", "unavailable", "disabled"}


def detect_size(name: str) -> str:
    for size, pattern in SIZE_RE.items():
        if pattern.search(name):
            return size
    return "unknown"


def detect_flavor(name: str) -> str:
    match = FLAVOR_RE.search(name)
    return match.group(0) if match else "classic"


def parse_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + CHINESE_NUMBERS[value[1]]
    if value.endswith("十") and len(value) == 2:
        return CHINESE_NUMBERS[value[0]] * 10
    if "十" in value and len(value) == 3:
        left, right = value.split("十")
        return CHINESE_NUMBERS[left] * 10 + CHINESE_NUMBERS[right]
    raise PlannerError(f"无法识别份数：{value}")


def validate_quantity(quantity: int) -> int:
    if not 1 <= quantity <= 20:
        raise PlannerError("份数必须在 1 到 20 之间；更大订单请拆分并人工核对")
    return quantity


def parse_request_text(text: str) -> OrderRequest:
    compact = re.sub(r"\s+", "", text).lower()
    preset_aliases = {
        "独奏": "solo",
        "二重奏": "duet",
        "分享装": "share",
        "多重奏": "share",
    }
    preset = next((value for key, value in preset_aliases.items() if key in compact), "custom")
    default_quantity, default_size = PRESETS.get(preset, (1, "medium"))
    if preset == "custom":
        # 未指定规格时按 auto 处理，优先中薯、再大薯、小薯，最后未知规格；
        # 避免菜单里只有“薯条”这种无规格名称时被误判为缺少规格。
        default_size = "auto"

    quantity = default_quantity
    number = r"(\d+|[一二两三四五六七八九十]{1,3})"
    patterns = (
        re.compile(number + r"(?:份|个|包)?(?:大|中|小)?薯"),
        re.compile(r"薯.*?" + number + r"(?:份|个|包)"),
    )
    for pattern in patterns:
        match = pattern.search(compact)
        if match:
            quantity = parse_number(match.group(1))
            break

    size = default_size
    for candidate, pattern in SIZE_RE.items():
        if pattern.search(compact):
            size = candidate
            break
    if "任意规格" in compact or "规格不限" in compact:
        size = "auto"

    keyword = None
    flavor = FLAVOR_RE.search(compact)
    if flavor:
        keyword = flavor.group(0)
    elif "原味" in compact or "经典" in compact:
        keyword = "classic"

    return OrderRequest(validate_quantity(quantity), size, keyword, preset)


def iter_dicts(value: Any, parent_key: str | None = None) -> Iterable[tuple[dict[str, Any], str | None]]:
    if isinstance(value, dict):
        yield value, parent_key
        for key, child in value.items():
            yield from iter_dicts(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child, parent_key)
    elif isinstance(value, str):
        stripped = value.strip()
        json_candidates: list[str] = []
        if stripped.startswith(("{", "[")):
            json_candidates.append(stripped)
        else:
            json_candidates.extend(match.group(0) for match in re.finditer(r"\{.*\}|\[.*\]", stripped, re.S))
        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            yield from iter_dicts(parsed, parent_key)


def extract_fries_products(payload: Any) -> list[FriesProduct]:
    products: dict[tuple[str, str], FriesProduct] = {}
    for data, parent_key in iter_dicts(payload):
        if is_unavailable(data):
            continue
        name_value = first_value(data, NAME_KEYS)
        code_value = first_value(data, CODE_KEYS)
        if code_value is None and isinstance(parent_key, str) and re.fullmatch(r"[A-Za-z0-9_-]{2,}", parent_key):
            code_value = parent_key
        if not isinstance(name_value, str) or code_value is None:
            continue
        name = name_value.strip()
        if not FRIES_RE.search(name) or EXCLUDE_RE.search(name):
            continue
        price = first_value(data, PRICE_KEYS)
        if price is None and not any(data.get(key) for key in STRONG_CODE_KEYS):
            continue
        code = str(code_value).strip()
        if not code:
            continue
        product = FriesProduct(
            code=code,
            name=name,
            size=detect_size(name),
            flavor=detect_flavor(name),
            menu_price_raw=price,
        )
        key = (code, name)
        previous = products.get(key)
        if previous is None or (previous.menu_price_raw is None and price is not None):
            products[key] = product
    return sorted(products.values(), key=lambda item: (item.name, item.code))


def choose_product(products: list[FriesProduct], request: OrderRequest) -> dict[str, Any]:
    if not products:
        return {
            "status": "no_fries_found",
            "message": "实时菜单中未识别到可售独立薯条商品，请检查门店、时段或原始字段。",
            "candidates": [],
        }

    candidates = products
    if request.keyword == "classic":
        candidates = [item for item in candidates if item.flavor == "classic"]
    elif request.keyword:
        candidates = [item for item in candidates if request.keyword.lower() in item.name.lower()]

    if not candidates:
        return {
            "status": "needs_clarification",
            "message": f"未找到符合风味“{request.keyword}”的薯条，请从现有风味中选择。",
            "candidates": [asdict(item) for item in products],
        }

    classic = [item for item in candidates if item.flavor == "classic"]
    if not request.keyword and classic:
        candidates = classic

    if request.size == "auto":
        for preferred in ("medium", "large", "small", "unknown"):
            sized = [item for item in candidates if item.size == preferred]
            if sized:
                candidates = sized
                break
    else:
        candidates = [item for item in candidates if item.size == request.size]

    if not candidates:
        return {
            "status": "needs_clarification",
            "message": f"当前候选中没有{request.size}规格；请改选实时可售规格。",
            "available_sizes": sorted({item.size for item in products}),
            "candidates": [asdict(item) for item in products],
        }

    flavor_groups = {item.flavor for item in candidates}
    if len(flavor_groups) > 1:
        return {
            "status": "needs_clarification",
            "message": "匹配到多个薯条风味，请选择一种。",
            "candidates": [asdict(item) for item in candidates],
        }

    if len({item.code for item in candidates}) > 1:
        return {
            "status": "needs_clarification",
            "message": "匹配到多个商品编码，请确认具体餐品，未自动替换或合并。",
            "candidates": [asdict(item) for item in candidates],
        }

    selected = candidates[0]
    return {
        "status": "ready_for_official_price",
        "request": asdict(request),
        "items": [{"code": selected.code, "name": selected.name, "quantity": request.quantity}],
        "selected_product": asdict(selected),
        "price_basis": "menu_price_raw_is_not_checkout_price; use calculate-price",
        "official_price_verified": False,
        "order_created": False,
    }


def build_plan(payload: Any, request: OrderRequest) -> dict[str, Any]:
    return choose_product(extract_fries_products(payload), request)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise PlannerError(f"菜单文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise PlannerError(f"菜单文件不是有效 JSON：{exc}") from exc


def write_result(result: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 query-meals JSON 生成薯条待算价计划")
    parser.add_argument("--menu", required=True, type=Path, help="query-meals 原始或归一化 JSON")
    parser.add_argument("--text", help="自然语言指令，例如：来三份大薯")
    parser.add_argument("--mode", choices=tuple(PRESETS), help="独奏 solo、二重奏 duet、分享装 share")
    parser.add_argument("--quantity", type=int, help="覆盖份数，范围 1-20")
    parser.add_argument("--size", choices=("auto", "small", "medium", "large"), help="覆盖规格")
    parser.add_argument("--keyword", help="风味关键词；classic 表示经典原味")
    parser.add_argument("--output", type=Path, help="可选的结果 JSON 路径")
    return parser


def resolve_request(args: argparse.Namespace) -> OrderRequest:
    if args.text:
        request = parse_request_text(args.text)
    else:
        quantity, size = PRESETS.get(args.mode or "custom", (1, "medium"))
        request = OrderRequest(quantity, size, None, args.mode or "custom")
    return OrderRequest(
        quantity=validate_quantity(args.quantity if args.quantity is not None else request.quantity),
        size=args.size or request.size,
        keyword=args.keyword if args.keyword is not None else request.keyword,
        preset=request.preset,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        request = resolve_request(args)
        result = build_plan(read_json(args.menu), request)
    except PlannerError as exc:
        parser.error(str(exc))
    write_result(result, args.output)
    return 0 if result["status"] == "ready_for_official_price" else 2


if __name__ == "__main__":
    raise SystemExit(main())
