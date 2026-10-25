from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_share_card import (  # noqa: E402
    build_caption,
    build_persona,
    build_review,
    load_summary,
    render_card,
    total_quantity,
)

SAMPLE = ROOT / "examples" / "order-summary.sample.json"


class PersonaTests(unittest.TestCase):
    def test_total_quantity(self):
        summary = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(total_quantity(summary), 3)

    def test_solo_persona(self):
        summary = {"items": [{"name": "中薯条", "quantity": 1}], "total_yuan": 14.5}
        self.assertEqual(build_persona(summary)[0], "独奏家")

    def test_duet_persona(self):
        summary = {"items": [{"name": "中薯条", "quantity": 2}], "total_yuan": 29.0}
        self.assertEqual(build_persona(summary)[0], "二重奏指挥")

    def test_ensemble_persona(self):
        summary = {"items": [{"name": "中薯条", "quantity": 4}], "total_yuan": 58.0}
        self.assertEqual(build_persona(summary)[0], "多重奏作曲家")

    def test_orchestra_persona(self):
        summary = {"items": [{"name": "中薯条", "quantity": 5}], "total_yuan": 72.5}
        self.assertEqual(build_persona(summary)[0], "薯条乐团团长")

    def test_mixed_review_mentions_multiple_parts(self):
        summary = {
            "items": [{"name": "中薯条", "quantity": 2}, {"name": "大薯条", "quantity": 1}],
            "total_yuan": 46.0,
        }
        self.assertIn("多声部", build_review(summary))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.summary = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_render_contains_key_fields(self):
        page = render_card(self.summary)
        self.assertIn("薯条多重奏", page)
        self.assertIn("麦当劳北京新东安二号餐厅", page)
        self.assertIn("¥42.50", page)
        self.assertIn("价格确认卡 · 尚未下单", page)
        self.assertIn("中薯条", page)

    def test_created_order_status(self):
        summary = dict(self.summary, created_order=True)
        page = render_card(summary)
        self.assertIn("订单已创建", page)

    def test_escapes_untrusted_html(self):
        summary = dict(self.summary)
        summary["store"] = "<script>alert(1)</script>"
        page = render_card(summary)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_caption_is_escaped_in_attribute(self):
        summary = dict(self.summary)
        summary["store"] = '门店" onclick="alert(1)'
        page = render_card(summary)
        self.assertNotIn('onclick="alert(1)"', page)
        self.assertIn("&quot;", page)

    def test_no_external_resources(self):
        page = render_card(self.summary)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_caption_contains_persona_and_total(self):
        caption = build_caption(self.summary)
        self.assertIn("多重奏作曲家", caption)
        self.assertIn("¥42.50", caption)

    def test_theme_is_selectable(self):
        page = render_card(self.summary, "midnight")
        self.assertIn("#241B18", page)


class LoadTests(unittest.TestCase):
    def test_rejects_missing_items(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"total_yuan": 1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_summary(path)

    def test_rejects_zero_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"items":[{"name":"薯条","quantity":0}],"total_yuan":1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_summary(path)


if __name__ == "__main__":
    unittest.main()
