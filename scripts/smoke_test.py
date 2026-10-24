#!/usr/bin/env python3
"""Read-only end-to-end smoke test for fries-ensemble.

Runs the ordering chain up to official pricing WITHOUT creating an order:
now-time-info -> query-nearby-stores -> query-meals -> query-meal-detail ->
fries_planner -> calculate-price.

Credentials come only from the MCD_MCP_TOKEN environment variable and are
never written to disk. This script never calls create-order or any write tool.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fries_planner import OrderRequest, build_plan  # noqa: E402
from mcp_client import MCPError, ReadOnlyMCPClient  # noqa: E402


def env_or(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def main() -> int:
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        sys.stderr.write("错误：未设置 MCD_MCP_TOKEN，冒烟测试中止（不会联网）\n")
        return 1
    city = env_or("MCD_CITY", "北京")
    keyword = env_or("MCD_KEYWORD", "王府井")
    quantity = int(env_or("MCD_QUANTITY", "3"))
    report_path = Path(env_or("MCD_REPORT", str(ROOT / "artifacts" / "smoke-report.json")))

    report: dict = {"status": "running", "created_order": False}
    try:
        client = ReadOnlyMCPClient(token)
        client.initialize()

        report["now"] = client.call_tool("now-time-info", {})

        store_code = os.environ.get("MCD_STORE_CODE", "").strip()
        store_name = None
        if store_code:
            store_name = os.environ.get("MCD_STORE_NAME", "").strip() or store_code
        else:
            stores = client.call_tool(
                "query-nearby-stores",
                {"beType": 1, "searchType": 2, "city": city, "keyword": keyword},
            )
            first_store = _first_store(stores)
            if not first_store:
                report["status"] = "no_store_found"
                _write(report, report_path)
                return 2
            store_code = first_store["storeCode"]
            store_name = first_store["storeName"]
        report["store"] = {"storeCode": store_code, "storeName": store_name}

        meals = client.call_tool(
            "query-meals",
            {"storeCode": store_code, "orderType": 1, "beType": 1},
        )
        plan = build_plan(meals, OrderRequest(quantity=quantity, size="auto"))
        report["plan_status"] = plan.get("status")
        if plan.get("status") != "ready_for_official_price":
            report["plan"] = plan
            report["status"] = "plan_not_ready"
            _write(report, report_path)
            return 3
        item = plan["items"][0]
        report["items"] = plan["items"]

        detail = client.call_tool(
            "query-meal-detail",
            {"storeCode": store_code, "orderType": 1, "beType": 1, "code": item["code"]},
        )
        report["meal_name"] = _detail_name(detail) or plan["selected_product"]["name"]

        price = client.call_tool(
            "calculate-price",
            {
                "storeCode": store_code,
                "orderType": 1,
                "beType": 1,
                "items": [{"productCode": item["code"], "quantity": item["quantity"]}],
                "needTableware": False,
            },
        )
        report["price"] = _price_summary(price)
        report["status"] = "ok"
        _write(report, report_path)
        print(json.dumps({"status": "ok", "store": store_name, "items": plan["items"], "price": report["price"]}, ensure_ascii=False, indent=2))
        return 0
    except MCPError as exc:
        report["status"] = "error"
        report["error"] = str(exc).replace(token, "[REDACTED]")
        _write(report, report_path)
        sys.stderr.write("错误：" + report["error"] + "\n")
        return 1


def _first_store(payload):
    for data in _walk(payload):
        if isinstance(data, dict) and data.get("storeCode") and data.get("storeName"):
            return {"storeCode": str(data["storeCode"]), "storeName": str(data["storeName"])}
    return None


def _detail_name(payload):
    for data in _walk(payload):
        if isinstance(data, dict) and data.get("code") and isinstance(data.get("name"), str):
            return str(data["name"])
    return None


def _price_summary(payload):
    target = None
    for data in _walk(payload):
        if isinstance(data, dict) and "price" in data and isinstance(data.get("price"), (int, float)):
            if "productList" in data or "originalPrice" in data:
                target = data
                break
    if not target:
        return None
    price_cents = target.get("price")
    original_cents = target.get("originalPrice")
    discount_cents = target.get("discount")
    return {
        "price_cents": price_cents,
        "price_yuan": round(price_cents / 100, 2) if isinstance(price_cents, (int, float)) else None,
        "original_price_cents": original_cents,
        "discount_cents": discount_cents,
    }


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return
            yield from _walk(parsed)


def _write(report, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
