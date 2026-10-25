#!/usr/bin/env python3
"""Local fries history and quantity-based achievements.

Only aggregate fries quantities and non-sensitive order context are stored.
The default history file is ~/.fries-ensemble/history.json. No network calls.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

MILESTONES = [
    (1, "初响", "FIRST NOTE", "完成第一份薯条记录。"),
    (10, "小型合奏", "ENSEMBLE", "累计 10 份，开始有自己的节奏。"),
    (25, "薯条常客", "REGULAR", "累计 25 份，熟悉的味道已经形成。"),
    (50, "多重奏指挥", "CONDUCTOR", "累计 50 份，足以指挥一桌人的薯条。"),
    (100, "百薯乐团", "CENTURY ORCHESTRA", "累计 100 份，薯条档案进入三位数。"),
    (200, "薯条传奇", "LEGEND", "累计 200 份，名字值得写进菜单边角。"),
    (500, "薯条宇宙", "UNIVERSE", "累计 500 份，脆响成为日常背景音。"),
]
BASE_RANK = {"threshold": 0, "name": "未开演", "code": "OVERTURE", "description": "还没有薯条记录。"}


def default_history_path() -> Path:
    configured = os.environ.get("FRIES_HISTORY_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".fries-ensemble" / "history.json"


def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"history file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("history file must contain a records array")
    return data


def save_history(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def add_record(
    path: Path,
    quantity: int,
    items: list[dict[str, Any]] | None = None,
    store: str | None = None,
    total_yuan: float | None = None,
    record_date: str | None = None,
    source: str = "manual",
    note: str | None = None,
) -> dict[str, Any]:
    if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 100:
        raise ValueError("quantity must be an integer between 1 and 100")
    if source not in {"order", "manual"}:
        raise ValueError("source must be order or manual")
    normalized_items = items or [{"name": "薯条", "quantity": quantity}]
    for item in normalized_items:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            raise ValueError("each item needs a name")
        item_quantity = item.get("quantity")
        if not isinstance(item_quantity, int) or isinstance(item_quantity, bool) or item_quantity < 1:
            raise ValueError("each item quantity must be a positive integer")
    if sum(int(item["quantity"]) for item in normalized_items) != quantity:
        raise ValueError("item quantities must add up to quantity")
    if note and len(note) > 80:
        raise ValueError("note must be 80 characters or fewer")
    if record_date is None:
        record_date = datetime.now().astimezone().date().isoformat()
    else:
        record_date = validate_date(record_date)

    data = load_history(path)
    record = {
        "id": uuid.uuid4().hex[:12],
        "date": record_date,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "quantity": quantity,
        "items": [{"name": str(item["name"]).strip(), "quantity": int(item["quantity"])} for item in normalized_items],
        "source": source,
    }
    if store:
        record["store"] = str(store).strip()[:80]
    if total_yuan is not None:
        if not isinstance(total_yuan, (int, float)) or isinstance(total_yuan, bool) or total_yuan < 0:
            raise ValueError("total_yuan must be a non-negative number")
        record["total_yuan"] = round(float(total_yuan), 2)
    if note:
        record["note"] = note.strip()
    data["records"].append(record)
    save_history(path, data)
    return record


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    records = data.get("records", [])
    total = sum(int(record.get("quantity", 0)) for record in records)
    unlocked = [
        {"threshold": threshold, "name": name, "code": code, "description": description}
        for threshold, name, code, description in MILESTONES
        if total >= threshold
    ]
    current = unlocked[-1] if unlocked else dict(BASE_RANK)
    next_milestone = next(
        (
            {"threshold": threshold, "name": name, "code": code, "description": description, "remaining": threshold - total}
            for threshold, name, code, description in MILESTONES
            if total < threshold
        ),
        None,
    )
    if next_milestone:
        previous = current["threshold"]
        span = max(1, next_milestone["threshold"] - previous)
        progress = round((total - previous) / span * 100, 1)
        progress = max(0.0, min(100.0, progress))
    else:
        progress = 100.0
    dates = sorted(str(record.get("date")) for record in records if record.get("date"))
    return {
        "total_quantity": total,
        "record_count": len(records),
        "average_quantity": round(total / len(records), 2) if records else 0,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "current_rank": current,
        "next_milestone": next_milestone,
        "progress_percent": progress,
        "unlocked": unlocked,
        "milestones": [
            {
                "threshold": threshold,
                "name": name,
                "code": code,
                "description": description,
                "unlocked": total >= threshold,
            }
            for threshold, name, code, description in MILESTONES
        ],
    }


def render_text(summary: dict[str, Any], recent: list[dict[str, Any]] | None = None) -> str:
    lines = [
        "薯条档案",
        f"累计份数：{summary['total_quantity']} 份",
        f"当前称号：{summary['current_rank']['name']}",
    ]
    next_milestone = summary.get("next_milestone")
    if next_milestone:
        lines.append(
            f"下一成就：{next_milestone['name']}（{summary['total_quantity']}/{next_milestone['threshold']}，还差 {next_milestone['remaining']} 份）"
        )
        filled = int(summary["progress_percent"] / 5)
        lines.append("进度：[" + "#" * filled + "-" * (20 - filled) + f"] {summary['progress_percent']:.1f}%")
    else:
        lines.append("已达到当前全部成就。")
    lines.append("成就：")
    for milestone in summary["milestones"]:
        mark = "[已解锁]" if milestone["unlocked"] else "[待解锁]"
        lines.append(f"  {mark} {milestone['threshold']:>3} 份 · {milestone['name']}")
    if recent:
        lines.append("最近记录：")
        for record in recent:
            lines.append(
                f"  {record.get('date', '')} · {record.get('quantity', 0)} 份 · {record.get('store', '未记录门店')}"
            )
    return "\n".join(lines)


def _badge_cards(summary: dict[str, Any]) -> str:
    cards = []
    for milestone in summary["milestones"]:
        state = "unlocked" if milestone["unlocked"] else "locked"
        marker = "已解锁" if milestone["unlocked"] else f"还差 {milestone['threshold'] - summary['total_quantity']} 份"
        cards.append(
            f'<article class="badge {state}">'
            f'<div class="badge-threshold">{milestone["threshold"]}<span>份</span></div>'
            f'<h3>{html.escape(milestone["name"])}</h3>'
            f'<p>{html.escape(milestone["code"])}</p>'
            f'<small>{html.escape(marker)}</small>'
            "</article>"
        )
    return "".join(cards)


def _record_rows(records: list[dict[str, Any]]) -> str:
    if not records:
        return '<tr><td colspan="5" class="empty">还没有记录。完成一次下单，或手动补录历史。</td></tr>'
    rows = []
    for record in records:
        items = "、".join(f"{item['name']}×{item['quantity']}" for item in record.get("items", []))
        total = record.get("total_yuan")
        total_text = f"¥{float(total):.2f}" if isinstance(total, (int, float)) else "-"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(record.get('date', '')))}</td>"
            f"<td>{html.escape(str(record.get('store', '未记录门店')))}</td>"
            f"<td>{html.escape(items or '薯条')}</td>"
            f"<td>{int(record.get('quantity', 0))}</td>"
            f"<td>{html.escape(total_text)}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_html(summary: dict[str, Any], records: list[dict[str, Any]], title: str = "薯条档案") -> str:
    total = summary["total_quantity"]
    current = html.escape(summary["current_rank"]["name"])
    next_milestone = summary.get("next_milestone")
    if next_milestone:
        next_text = f"距离「{html.escape(next_milestone['name'])}」还差 {next_milestone['remaining']} 份"
    else:
        next_text = "全部成就已解锁"
    recent = sorted(records, key=lambda item: (str(item.get("date", "")), str(item.get("recorded_at", ""))), reverse=True)[:8]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{
    --cream: #F6E7CC; --paper: #FFFDF7; --ink: #2A1A12; --muted: #7A6558;
    --red: #C8102E; --gold: #F2B705; --soft: #F9D98A; --line: #E7D5BA;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 28px 16px; min-height: 100vh;
    background: var(--cream); color: var(--ink);
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  }}
  .page {{ width: min(96vw, 860px); margin: 0 auto; background: var(--paper); border-radius: 28px; overflow: hidden; box-shadow: 0 24px 80px rgba(42, 26, 18, .14); }}
  .stripe {{ height: 10px; background: var(--red); }}
  .inner {{ padding: 36px 40px 30px; }}
  .eyebrow {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: .18em; text-transform: uppercase; }}
  h1 {{ margin: 14px 0 2px; font-size: clamp(38px, 7vw, 62px); line-height: 1; letter-spacing: -.04em; }}
  .sub {{ margin: 0; color: var(--muted); font-size: 14px; }}
  .hero {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 28px 0 24px; }}
  .stat {{ background: var(--soft); border-radius: 20px; padding: 20px 22px; }}
  .stat small {{ display: block; color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .08em; }}
  .stat strong {{ display: block; margin-top: 6px; font-size: clamp(40px, 8vw, 64px); line-height: .9; letter-spacing: -.05em; }}
  .stat strong em {{ font-style: normal; font-size: 18px; letter-spacing: 0; color: var(--muted); margin-left: 6px; }}
  .rank {{ background: var(--ink); color: #fff; border-radius: 20px; padding: 20px 22px; }}
  .rank small {{ color: #D8C4A8; display: block; font-size: 12px; font-weight: 700; letter-spacing: .08em; }}
  .rank strong {{ display: block; margin-top: 8px; font-size: clamp(30px, 6vw, 44px); line-height: 1.05; }}
  .rank span {{ display: block; margin-top: 8px; color: #D8C4A8; font-size: 13px; }}
  .progress {{ margin: 6px 0 26px; }}
  .progress-head {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 12px; font-weight: 700; }}
  .bar {{ height: 12px; margin-top: 8px; background: var(--line); border-radius: 999px; overflow: hidden; }}
  .bar i {{ display: block; height: 100%; width: {summary['progress_percent']}%; background: var(--red); border-radius: inherit; }}
  h2 {{ margin: 0 0 12px; font-size: 18px; }}
  .badges {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .badge {{ border: 1px solid var(--line); border-radius: 16px; padding: 14px; min-height: 132px; background: #fff; }}
  .badge.unlocked {{ border-color: var(--gold); box-shadow: inset 0 3px 0 var(--gold); }}
  .badge.locked {{ opacity: .52; }}
  .badge-threshold {{ font-size: 28px; font-weight: 900; letter-spacing: -.03em; color: var(--red); }}
  .badge-threshold span {{ margin-left: 2px; font-size: 11px; font-weight: 700; color: var(--muted); }}
  .badge h3 {{ margin: 8px 0 2px; font-size: 14px; }}
  .badge p {{ margin: 0; color: var(--muted); font-size: 10px; letter-spacing: .08em; }}
  .badge small {{ display: block; margin-top: 10px; color: var(--muted); font-size: 11px; }}
  .badge.unlocked small {{ color: var(--red); font-weight: 700; }}
  .records {{ margin-top: 26px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ color: var(--muted); font-size: 11px; text-align: left; letter-spacing: .08em; padding: 8px 6px; border-bottom: 1px solid var(--line); }}
  td {{ padding: 10px 6px; border-bottom: 1px solid #F0E6D6; }}
  td:last-child, th:last-child {{ text-align: right; }}
  .empty {{ color: var(--muted); text-align: center !important; padding: 20px; }}
  .footer {{ margin-top: 26px; padding-top: 16px; border-top: 1px dashed var(--line); color: var(--muted); font-size: 11px; line-height: 1.7; display: flex; justify-content: space-between; gap: 16px; }}
  @media (max-width: 620px) {{
    .inner {{ padding: 26px 22px 24px; }}
    .hero {{ grid-template-columns: 1fr; }}
    .badges {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>
<main class="page">
  <div class="stripe"></div>
  <div class="inner">
    <div class="eyebrow"><span>Fries Archive</span><span>Local Only</span></div>
    <h1>薯条档案</h1>
    <p class="sub">吃过的每一份，都在这里留下一个节拍。</p>

    <section class="hero">
      <div class="stat">
        <small>累计份数</small>
        <strong>{total}<em>份</em></strong>
      </div>
      <div class="rank">
        <small>当前称号</small>
        <strong>{current}</strong>
        <span>{next_text}</span>
      </div>
    </section>

    <section class="progress">
      <div class="progress-head"><span>当前进度 {summary['progress_percent']:.1f}%</span><span>{summary['record_count']} 条记录</span></div>
      <div class="bar"><i></i></div>
    </section>

    <h2>成就图谱</h2>
    <section class="badges">{_badge_cards(summary)}</section>

    <section class="records">
      <h2>最近记录</h2>
      <table>
        <thead><tr><th>日期</th><th>门店</th><th>内容</th><th>份数</th><th>金额</th></tr></thead>
        <tbody>{_record_rows(recent)}</tbody>
      </table>
    </section>

    <footer class="footer">
      <span>数据仅保存在本机历史文件中，不上传账户信息。</span>
      <span>非麦当劳官方产品</span>
    </footer>
  </div>
</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地薯条历史与累计成就")
    parser.add_argument("--data", type=Path, default=default_history_path(), help="历史文件路径；默认 ~/.fries-ensemble/history.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="添加一条历史记录")
    add.add_argument("--quantity", required=True, type=int, help="总份数")
    add.add_argument("--name", default="薯条", help="商品名称，默认“薯条”")
    add.add_argument("--store", help="门店名称；不要写手机号或详细地址")
    add.add_argument("--total", type=float, dest="total_yuan", help="本次官方实付金额，单位元")
    add.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    add.add_argument("--source", choices=("order", "manual"), default="manual", help="记录来源")
    add.add_argument("--note", help="可选备注，最多 80 字；不要写敏感信息")
    add.add_argument("--items-file", type=Path, help="混合商品 JSON 数组，例如 [{\"name\":\"中薯条\",\"quantity\":2}]")

    summary = subparsers.add_parser("summary", help="查看累计份数与成就")
    summary.add_argument("--json", action="store_true", help="输出 JSON")
    summary.add_argument("--html", type=Path, help="同时生成成就页 HTML")
    summary.add_argument("--limit", type=int, default=5, help="文本模式展示最近记录条数")

    listing = subparsers.add_parser("list", help="列出历史记录")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--json", action="store_true")

    subparsers.add_parser("path", help="显示历史文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.data = args.data.expanduser()
    if getattr(args, "items_file", None):
        args.items_file = args.items_file.expanduser()
    if getattr(args, "html", None):
        args.html = args.html.expanduser()
    try:
        data = load_history(args.data)
        if args.command == "add":
            items = None
            if args.items_file:
                items = json.loads(args.items_file.read_text(encoding="utf-8-sig"))
                if not isinstance(items, list):
                    raise ValueError("items-file must contain a JSON array")
            record = add_record(
                args.data,
                quantity=args.quantity,
                items=items,
                store=args.store,
                total_yuan=args.total_yuan,
                record_date=args.date,
                source=args.source,
                note=args.note,
            )
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return 0
        if args.command == "path":
            print(str(args.data))
            return 0
        if args.command == "list":
            records = sorted(
                data["records"],
                key=lambda item: (str(item.get("date", "")), str(item.get("recorded_at", ""))),
                reverse=True,
            )[: args.limit]
            if args.json:
                print(json.dumps(records, ensure_ascii=False, indent=2))
            else:
                for record in records:
                    print(f"{record.get('date', '')} · {record.get('quantity', 0)} 份 · {record.get('store', '未记录门店')}")
            return 0
        summary = summarize(data)
        if args.html:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(render_html(summary, data["records"]), encoding="utf-8")
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            records = sorted(
                data["records"],
                key=lambda item: (str(item.get("date", "")), str(item.get("recorded_at", ""))),
                reverse=True,
            )[: args.limit]
            print(render_text(summary, records))
        if args.html:
            print(f"成就页：{args.html}")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("错误：" + str(exc) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
