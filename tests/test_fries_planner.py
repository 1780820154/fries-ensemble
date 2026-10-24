from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fries_planner import (  # noqa: E402
    OrderRequest,
    PlannerError,
    build_plan,
    extract_fries_products,
    parse_request_text,
    read_json,
    validate_quantity,
)


FIXTURE = ROOT / "tests" / "fixtures" / "menu.sample.json"


class RequestParsingTests(unittest.TestCase):
    def test_solo_preset(self):
        request = parse_request_text("薯条独奏")
        self.assertEqual((request.quantity, request.size, request.preset), (1, "medium", "solo"))

    def test_duet_preset(self):
        request = parse_request_text("来个点薯条的二重奏")
        self.assertEqual((request.quantity, request.size), (2, "medium"))

    def test_share_alias(self):
        request = parse_request_text("薯条多重奏")
        self.assertEqual((request.quantity, request.preset), (4, "share"))

    def test_chinese_quantity_and_size(self):
        request = parse_request_text("来三份大薯")
        self.assertEqual((request.quantity, request.size), (3, "large"))

    def test_arabic_quantity_after_product(self):
        request = parse_request_text("薯条 4 份，小份")
        self.assertEqual((request.quantity, request.size), (4, "small"))

    def test_flavor_and_auto_size(self):
        request = parse_request_text("来一份海苔摇摇薯条，规格不限")
        self.assertEqual((request.quantity, request.size, request.keyword), (1, "auto", "海苔"))

    def test_classic_keyword(self):
        self.assertEqual(parse_request_text("两份原味中薯").keyword, "classic")

    def test_twelve_quantity(self):
        self.assertEqual(parse_request_text("十二份大薯").quantity, 12)

    def test_quantity_lower_bound(self):
        with self.assertRaises(PlannerError):
            validate_quantity(0)

    def test_quantity_upper_bound(self):
        with self.assertRaises(PlannerError):
            parse_request_text("二十一份大薯")


class MenuExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.products = extract_fries_products(cls.payload)

    def test_extracts_real_fries(self):
        codes = {item.code for item in self.products}
        self.assertTrue({"FRIES-S-DEMO", "FRIES-M-DEMO", "FRIES-L-DEMO"}.issubset(codes))

    def test_excludes_combo_hashbrown_and_sold_out(self):
        codes = {item.code for item in self.products}
        self.assertNotIn("COMBO-DEMO", codes)
        self.assertNotIn("HASH-DEMO", codes)
        self.assertNotIn("SOLD-OUT-DEMO", codes)

    def test_detects_sizes(self):
        sizes = {item.code: item.size for item in self.products}
        self.assertEqual(sizes["FRIES-S-DEMO"], "small")
        self.assertEqual(sizes["FRIES-M-DEMO"], "medium")
        self.assertEqual(sizes["FRIES-L-DEMO"], "large")

    def test_parses_embedded_mcp_json_text(self):
        payload = {"content": [{"type": "text", "text": json.dumps(self.payload, ensure_ascii=False)}]}
        self.assertGreaterEqual(len(extract_fries_products(payload)), 4)

    def test_parses_markdown_prefixed_embedded_json(self):
        embedded = "# API Response\n\n说明文本\n" + json.dumps(self.payload, ensure_ascii=False)
        payload = {"content": [{"type": "text", "text": embedded}]}
        self.assertGreaterEqual(len(extract_fries_products(payload)), 4)

    def test_parses_meals_keyed_by_code(self):
        payload = {
            "data": {
                "meals": {
                    "4810": {
                        "name": "薯条",
                        "currentPrice": "14.5",
                        "originalPrice": "14.5",
                        "canWithOrder": False,
                    }
                }
            }
        }
        products = extract_fries_products(payload)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].code, "4810")
        self.assertEqual(products[0].menu_price_raw, "14.5")

    def test_ignores_category_without_product_evidence(self):
        payload = {"categories": [{"id": "cat-1", "name": "薯条"}]}
        self.assertEqual(extract_fries_products(payload), [])


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_default_plan_requires_official_price(self):
        plan = build_plan(self.payload, OrderRequest(quantity=2, size="medium"))
        self.assertEqual(plan["status"], "ready_for_official_price")
        self.assertEqual(plan["items"], [{"code": "FRIES-M-DEMO", "name": "薯条（中）", "quantity": 2}])
        self.assertFalse(plan["official_price_verified"])
        self.assertFalse(plan["order_created"])

    def test_large_plan(self):
        plan = build_plan(self.payload, OrderRequest(quantity=3, size="large"))
        self.assertEqual(plan["items"][0]["code"], "FRIES-L-DEMO")
        self.assertEqual(plan["items"][0]["quantity"], 3)

    def test_flavored_plan_with_auto_size(self):
        plan = build_plan(self.payload, OrderRequest(quantity=1, size="auto", keyword="海苔"))
        self.assertEqual(plan["status"], "ready_for_official_price")
        self.assertEqual(plan["items"][0]["code"], "SHAKE-SEAWEED-DEMO")

    def test_unknown_flavor_returns_choices(self):
        plan = build_plan(self.payload, OrderRequest(keyword="松露"))
        self.assertEqual(plan["status"], "needs_clarification")
        self.assertGreater(len(plan["candidates"]), 0)

    def test_missing_size_does_not_silently_substitute(self):
        payload = [{"mealCode": "M", "mealName": "薯条（中）", "price": "1"}]
        plan = build_plan(payload, OrderRequest(size="large"))
        self.assertEqual(plan["status"], "needs_clarification")
        self.assertIn("medium", plan["available_sizes"])

    def test_multiple_codes_require_clarification(self):
        payload = [
            {"mealCode": "A", "mealName": "薯条（中）", "price": "1"},
            {"mealCode": "B", "mealName": "经典薯条（中）", "price": "1"},
        ]
        plan = build_plan(payload, OrderRequest())
        self.assertEqual(plan["status"], "needs_clarification")
        self.assertEqual(len(plan["candidates"]), 2)

    def test_no_fries(self):
        plan = build_plan({"meals": []}, OrderRequest())
        self.assertEqual(plan["status"], "no_fries_found")

    def test_invalid_menu_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(PlannerError):
                read_json(path)


if __name__ == "__main__":
    unittest.main()
