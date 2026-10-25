#!/usr/bin/env python3
"""Render a shareable fries-ensemble price card from a normalized summary.

The generator is offline and never calls MCP. It does not include tokens,
phone numbers, addresses, payment links, or account data.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

THEMES = {
    "concert": {
        "bg": "#F6E7CC",
        "paper": "#FFFDF7",
        "ink": "#2A1A12",
        "muted": "#7A6558",
        "accent": "#C8102E",
        "gold": "#F2B705",
        "soft": "#F9D98A",
    },
    "midnight": {
        "bg": "#241B18",
        "paper": "#2F2521",
        "ink": "#FFF6E8",
        "muted": "#C8B8A7",
        "accent": "#F2B705",
        "gold": "#F2B705",
        "soft": "#5A4030",
    },
    "picnic": {
        "bg": "#EAF0DE",
        "paper": "#FFFDF4",
        "ink": "#233020",
        "muted": "#66735A",
        "accent": "#B23A2B",
        "gold": "#E0A800",
        "soft": "#F1D98C",
    },
}


def load_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"summary file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"summary is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("summary must be a JSON object")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("summary.items must be a non-empty array")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each item must be an object")
        name = item.get("name")
        quantity = item.get("quantity")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("item.name is required")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError("item.quantity must be a positive integer")
    total = data.get("total_yuan")
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total < 0:
        raise ValueError("summary.total_yuan must be a non-negative number")
    return data


def total_quantity(summary: dict[str, Any]) -> int:
    return sum(int(item["quantity"]) for item in summary["items"])


def build_persona(summary: dict[str, Any]) -> tuple[str, str]:
    quantity = total_quantity(summary)
    distinct = len({str(item["name"]).strip() for item in summary["items"]})
    if quantity == 1:
        return "独奏家", "一份也能成立，脆响是今天最短的间奏。"
    if quantity == 2:
        return "二重奏指挥", "两份刚好成拍，适合一人一份，也适合分着听。"
    if quantity <= 4:
        return "多重奏作曲家", "三到四份是桌面上的小型合奏，趁热听完最合适。"
    return "薯条乐团团长", "这是一整支薯条乐团，唯一的指挥是趁热。"


def build_review(summary: dict[str, Any]) -> str:
    persona, base = build_persona(summary)
    distinct = len({str(item["name"]).strip() for item in summary["items"]})
    if distinct > 1:
        return f"{base} 多声部同时上场，口感从第一口到最后一口都不重样。"
    return f"{base} {persona}的今日曲目，简单但不会出错。"


def build_caption(summary: dict[str, Any]) -> str:
    persona, _ = build_persona(summary)
    items_text = "、".join(f"{item['name']} ×{item['quantity']}" for item in summary["items"])
    total = float(summary["total_yuan"])
    return (
        f"我的薯条人格是「{persona}」：{items_text}，官方算价 ¥{total:.2f}。"
        f"{build_review(summary)} #薯条多重奏 #麦当劳MCP"
    )


def _fmt_money(value: Any) -> str:
    try:
        return f"¥{float(value):.2f}"
    except (TypeError, ValueError):
        return "¥--"


def _status_text(summary: dict[str, Any]) -> str:
    return "订单已创建" if summary.get("created_order") is True else "价格确认卡 · 尚未下单"


def render_card(summary: dict[str, Any], theme_name: str = "concert") -> str:
    theme = THEMES.get(theme_name, THEMES["concert"])
    persona, persona_line = build_persona(summary)
    review = build_review(summary)
    caption = build_caption(summary)
    store = html.escape(str(summary.get("store") or "麦当劳门店"))
    order_type = html.escape(str(summary.get("order_type") or "到店自取"))
    take_way = html.escape(str(summary.get("take_way") or "外带"))
    verified_at = html.escape(str(summary.get("price_verified_at") or "实时查询"))
    status = html.escape(_status_text(summary))
    total = _fmt_money(summary.get("total_yuan"))
    original = _fmt_money(summary.get("original_price_yuan"))
    discount_value = summary.get("discount_yuan")
    discount = _fmt_money(discount_value) if discount_value else "¥0.00"
    rows = "".join(
        f"<li><span>{html.escape(str(item['name']))}</span><strong>×{int(item['quantity'])}</strong></li>"
        for item in summary["items"]
    )
    item_count = total_quantity(summary)
    caption_attr = html.escape(caption, quote=True)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>薯条多重奏 · {html.escape(persona)}</title>
<style>
  :root {{
    --bg: {theme['bg']};
    --paper: {theme['paper']};
    --ink: {theme['ink']};
    --muted: {theme['muted']};
    --accent: {theme['accent']};
    --gold: {theme['gold']};
    --soft: {theme['soft']};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 28px 16px;
    background: var(--bg);
    color: var(--ink);
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  }}
  .card {{
    width: min(94vw, 720px);
    background: var(--paper);
    border: 1px solid color-mix(in srgb, var(--ink) 14%, transparent);
    border-radius: 28px;
    overflow: hidden;
    box-shadow: 0 24px 80px color-mix(in srgb, var(--ink) 16%, transparent);
  }}
  .stripe {{ height: 10px; background: var(--accent); }}
  .inner {{ padding: 34px 38px 30px; }}
  .eyebrow {{
    display: flex; justify-content: space-between; gap: 12px;
    font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
    color: var(--muted); font-weight: 700;
  }}
  h1 {{ margin: 14px 0 4px; font-size: clamp(38px, 7vw, 64px); line-height: .98; letter-spacing: -.04em; }}
  .sub {{ margin: 0; color: var(--muted); font-size: 14px; }}
  .hero {{
    display: grid; grid-template-columns: 148px 1fr; gap: 24px;
    align-items: center; margin: 28px 0 24px;
  }}
  .fries {{ width: 148px; height: 164px; }}
  .persona-label {{ margin: 0 0 8px; color: var(--accent); font-size: 12px; font-weight: 800; letter-spacing: .08em; }}
  .persona {{ margin: 0; font-size: clamp(28px, 5vw, 42px); line-height: 1.05; }}
  .persona-line {{ margin: 10px 0 0; color: var(--muted); font-size: 14px; line-height: 1.7; }}
  .order {{
    border-top: 1px dashed color-mix(in srgb, var(--ink) 20%, transparent);
    border-bottom: 1px dashed color-mix(in srgb, var(--ink) 20%, transparent);
    padding: 18px 0;
  }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px 22px; font-size: 14px; }}
  .meta div {{ display: flex; justify-content: space-between; gap: 12px; }}
  .meta span {{ color: var(--muted); }}
  .meta strong {{ text-align: right; }}
  ul {{ list-style: none; padding: 0; margin: 18px 0 0; }}
  li {{ display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid color-mix(in srgb, var(--ink) 8%, transparent); font-size: 16px; }}
  li:last-child {{ border-bottom: 0; }}
  li strong {{ color: var(--accent); }}
  .price {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 22px 0 8px; }}
  .price-label {{ color: var(--muted); font-size: 13px; font-weight: 700; letter-spacing: .08em; }}
  .price strong {{ display: block; margin-top: 4px; font-size: clamp(46px, 9vw, 72px); line-height: .9; letter-spacing: -.05em; }}
  .price small {{ display: block; margin-top: 10px; color: var(--muted); font-size: 13px; }}
  .stamp {{
    border: 2px solid var(--accent); color: var(--accent); border-radius: 999px;
    padding: 8px 14px; font-size: 12px; font-weight: 800; white-space: nowrap;
    transform: rotate(-4deg);
  }}
  blockquote {{
    margin: 18px 0 0; padding: 18px 20px; background: color-mix(in srgb, var(--soft) 40%, var(--paper));
    border-left: 4px solid var(--gold); border-radius: 0 14px 14px 0;
    font-size: 15px; line-height: 1.7;
  }}
  .footer {{ display: flex; justify-content: space-between; gap: 16px; margin-top: 20px; color: var(--muted); font-size: 11px; line-height: 1.6; }}
  button {{
    margin-top: 22px; width: 100%; border: 0; border-radius: 12px; padding: 14px 18px;
    background: var(--accent); color: #fff; font-size: 15px; font-weight: 800; cursor: pointer;
    font-family: inherit;
  }}
  button:active {{ transform: translateY(1px); }}
  .note {{ margin: 10px 0 0; text-align: center; color: var(--muted); font-size: 11px; }}
  @media (max-width: 560px) {{
    .inner {{ padding: 26px 22px 24px; }}
    .hero {{ grid-template-columns: 104px 1fr; gap: 16px; }}
    .fries {{ width: 104px; height: 120px; }}
    .meta {{ grid-template-columns: 1fr; }}
    .price {{ align-items: flex-start; flex-direction: column; }}
  }}
  @media (prefers-reduced-motion: no-preference) {{
    .fries .note {{ animation: float 3.6s ease-in-out infinite; transform-origin: center; }}
    @keyframes float {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-4px); }} }}
  }}
</style>
</head>
<body>
<article class="card">
  <div class="stripe"></div>
  <div class="inner">
    <div class="eyebrow"><span>Fries Ensemble</span><span>Price Card</span></div>
    <h1>薯条多重奏</h1>
    <p class="sub">把一顿薯条，听成一段乐章。</p>

    <section class="hero">
      <svg class="fries" viewBox="0 0 148 164" role="img" aria-label="薯条与音符插画">
        <g fill="none" stroke="{theme['soft']}" stroke-width="2" opacity=".8">
          <path d="M20 30 H128 M20 42 H128 M20 54 H128 M20 66 H128 M20 78 H128"/>
        </g>
        <g class="note" fill="{theme['accent']}">
          <circle cx="108" cy="44" r="6"/><path d="M113 44 V22 L129 18 V39" stroke="{theme['accent']}" stroke-width="3" fill="none"/>
          <circle cx="123" cy="40" r="5"/>
        </g>
        <g transform="translate(18 72)">
          <path d="M18 70 L10 108 H112 L104 70 Z" fill="{theme['accent']}"/>
          <path d="M18 70 L10 108 H112 L104 70 Z" fill="none" stroke="{theme['ink']}" stroke-width="2" opacity=".25"/>
          <g fill="{theme['gold']}">
            <rect x="30" y="8" width="12" height="70" rx="5" transform="rotate(-9 36 43)"/>
            <rect x="47" y="0" width="12" height="76" rx="5" transform="rotate(-3 53 38)"/>
            <rect x="64" y="6" width="12" height="72" rx="5" transform="rotate(4 70 42)"/>
            <rect x="81" y="12" width="12" height="66" rx="5" transform="rotate(10 87 45)"/>
          </g>
          <g fill="#fff" opacity=".28">
            <path d="M22 82 h76 l-3 14 H25 Z"/>
          </g>
          <text x="34" y="98" font-size="12" font-weight="800" fill="#fff" font-family="Microsoft YaHei, sans-serif">HOT</text>
        </g>
      </svg>
      <div>
        <p class="persona-label">你的薯条人格</p>
        <h2 class="persona">{html.escape(persona)}</h2>
        <p class="persona-line">{html.escape(persona_line)}</p>
      </div>
    </section>

    <section class="order">
      <div class="meta">
        <div><span>门店</span><strong>{store}</strong></div>
        <div><span>方式</span><strong>{order_type} · {take_way}</strong></div>
        <div><span>份数</span><strong>{item_count} 份</strong></div>
        <div><span>算价时间</span><strong>{verified_at}</strong></div>
      </div>
      <ul>{rows}</ul>
    </section>

    <section class="price">
      <div>
        <div class="price-label">官方算价</div>
        <strong>{total}</strong>
        <small>原价 {original} · 已优惠 {discount}</small>
      </div>
      <div class="stamp">{status}</div>
    </section>

    <blockquote>{html.escape(review)}</blockquote>

    <div class="footer">
      <span>数据来自麦当劳中国 MCP 实时返回。价格与供应状态以官方为准。</span>
      <span>非麦当劳官方产品</span>
    </div>

    <button id="copy" type="button" data-caption="{caption_attr}">复制分享文案</button>
    <p class="note">卡片不包含支付链接、手机号或账户信息。</p>
  </div>
</article>
<script>
  const button = document.getElementById("copy");
  button.addEventListener("click", async () => {{
    const caption = button.getAttribute("data-caption") || "";
    try {{
      await navigator.clipboard.writeText(caption);
      button.textContent = "已复制";
    }} catch (error) {{
      button.textContent = "请手动复制";
    }}
  }});
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成薯条多重奏价格确认分享卡")
    parser.add_argument("--summary", required=True, type=Path, help="归一化订单摘要 JSON")
    parser.add_argument("--output", required=True, type=Path, help="输出 HTML 路径")
    parser.add_argument("--theme", choices=tuple(THEMES), default="concert", help="卡片主题")
    args = parser.parse_args(argv)
    try:
        summary = load_summary(args.summary)
    except ValueError as exc:
        parser.error(str(exc))
    html_text = render_card(summary, args.theme)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
