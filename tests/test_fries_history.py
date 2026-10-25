from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fries_history import (  # noqa: E402
    add_record,
    load_history,
    render_html,
    render_text,
    summarize,
)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "history.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_history(self):
        summary = summarize(load_history(self.path))
        self.assertEqual(summary["total_quantity"], 0)
        self.assertEqual(summary["record_count"], 0)
        self.assertEqual(summary["current_rank"]["name"], "未开演")
        self.assertEqual(summary["next_milestone"]["name"], "初响")

    def test_add_and_reload(self):
        add_record(self.path, 3, store="门店 A", total_yuan=42.5, record_date="2026-10-24")
        add_record(self.path, 2, store="门店 B", total_yuan=29.0, record_date="2026-10-25")
        summary = summarize(load_history(self.path))
        self.assertEqual(summary["total_quantity"], 5)
        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(summary["current_rank"]["name"], "初响")
        self.assertEqual(summary["next_milestone"]["threshold"], 10)
        self.assertEqual(summary["next_milestone"]["remaining"], 5)

    def test_milestone_boundaries(self):
        add_record(self.path, 10, record_date="2026-10-24")
        summary = summarize(load_history(self.path))
        self.assertEqual(summary["current_rank"]["name"], "小型合奏")
        self.assertEqual(summary["next_milestone"]["threshold"], 25)

        add_record(self.path, 15, record_date="2026-10-25")
        summary = summarize(load_history(self.path))
        self.assertEqual(summary["current_rank"]["name"], "薯条常客")
        self.assertEqual(summary["next_milestone"]["threshold"], 50)

    def test_all_milestones_unlocked(self):
        add_record(self.path, 100, record_date="2026-10-24")
        add_record(self.path, 100, record_date="2026-10-25")
        add_record(self.path, 100, record_date="2026-10-25")
        add_record(self.path, 100, record_date="2026-10-25")
        add_record(self.path, 100, record_date="2026-10-25")
        summary = summarize(load_history(self.path))
        self.assertEqual(summary["total_quantity"], 500)
        self.assertEqual(summary["current_rank"]["name"], "薯条宇宙")
        self.assertIsNone(summary["next_milestone"])
        self.assertEqual(summary["progress_percent"], 100.0)

    def test_mixed_items(self):
        record = add_record(
            self.path,
            3,
            items=[{"name": "中薯条", "quantity": 2}, {"name": "大薯条", "quantity": 1}],
            record_date="2026-10-24",
        )
        self.assertEqual(record["items"][1]["name"], "大薯条")
        self.assertEqual(sum(load_history(self.path)["records"][0]["items"][i]["quantity"] for i in range(2)), 3)

    def test_item_sum_must_match_quantity(self):
        with self.assertRaises(ValueError):
            add_record(self.path, 3, items=[{"name": "中薯条", "quantity": 2}])

    def test_invalid_quantity(self):
        with self.assertRaises(ValueError):
            add_record(self.path, 0)

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            add_record(self.path, 1, record_date="2026/10/24")

    def test_render_text_contains_progress_and_achievements(self):
        add_record(self.path, 10, record_date="2026-10-24")
        summary = summarize(load_history(self.path))
        text = render_text(summary)
        self.assertIn("累计份数：10 份", text)
        self.assertIn("下一成就：薯条常客", text)
        self.assertIn("[已解锁]  10 份", text)
        self.assertIn("[待解锁]  25 份", text)

    def test_render_html_escapes_and_has_no_external_links(self):
        add_record(self.path, 3, store="<script>alert(1)</script>", record_date="2026-10-24")
        summary = summarize(load_history(self.path))
        page = render_html(summary, load_history(self.path)["records"])
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertIn("薯条档案", page)
        self.assertIn("初响", page)

    def test_json_roundtrip_has_no_sensitive_fields(self):
        add_record(self.path, 3, store="门店 A", total_yuan=42.5, record_date="2026-10-24")
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("token", raw.lower())
        self.assertNotIn("phone", raw.lower())
        self.assertNotIn("address", raw.lower())


if __name__ == "__main__":
    unittest.main()
