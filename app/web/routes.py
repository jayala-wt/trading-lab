from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, request, render_template_string

from core.common.env import load_dotenv
from core.common.paths import queue_dir, repo_root
from core.data.db import Database

trading_lab_bp = Blueprint("trading_lab", __name__, url_prefix="/trading-lab")

TABLE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, sans-serif; background: #0b1120; color: #e2e8f0; }
    a { color: #7dd3fc; text-decoration: none; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
    th, td { border-bottom: 1px solid #1f2937; padding: 8px; text-align: left; }
    th { background: #111827; }
    input { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; padding: 6px; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <div>
    <a href="/trading-lab/overview">Overview</a> |
    <a href="/trading-lab/bots">Bots</a> |
    <a href="/trading-lab/signals">Signals</a> |
    <a href="/trading-lab/trades">Trades</a> |
    <a href="/trading-lab/patterns">Patterns</a> |
    <a href="/trading-lab/strategies">Strategies</a> |
    <a href="/trading-lab/content-queue">Content Queue</a> |
    <a href="/trading-lab/devlog">Devlog</a>
  </div>
  {{ body|safe }}
</body>
</html>
"""


def _env(key: str, default: str) -> str:
    import os

    return os.getenv(key, default)


def _db() -> Database:
    load_dotenv(repo_root() / ".env")
    db_path = Path(_env("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    return Database(db_path)


def _query_rows(table: str, limit: int = 200, search: str | None = None) -> List[Dict[str, Any]]:
    db = _db()
    sql = f"SELECT * FROM {table}"
    params: List[Any] = []
    if search:
        sql += " WHERE " + " OR ".join([f"{col} LIKE ?" for col in _columns(table)])
        params.extend([f"%{search}%"] * len(_columns(table)))
    sql += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    rows = db.query(sql, tuple(params))
    return [dict(row) for row in rows]


def _columns(table: str) -> List[str]:
    db = _db()
    rows = db.query(f"PRAGMA table_info({table})")
    return [row["name"] for row in rows]


def _render_table(title: str, rows: List[Dict[str, Any]], search: str | None = None) -> str:
    search = search or ""
    search_form = (
        "<form method=\"get\">"
        f"<input type=\"text\" name=\"q\" value=\"{search}\" placeholder=\"search\"/>"
        "<input type=\"submit\" value=\"Filter\"/>"
        "</form>"
    )
    if not rows:
        return render_template_string(TABLE_TEMPLATE, title=title, body=search_form + "<p>No data.</p>")
    headers = rows[0].keys()
    body = ["<table>"]
    body.append("<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{row.get(h, '')}</td>" for h in headers) + "</tr>")
    body.append("</table>")
    return render_template_string(TABLE_TEMPLATE, title=title, body=search_form + "".join(body))


@trading_lab_bp.route("/overview")
def overview() -> str:
    db = _db()
    counts = {
        "bots": db.query("SELECT COUNT(*) as count FROM bots")[0]["count"],
        "signals": db.query("SELECT COUNT(*) as count FROM signals")[0]["count"],
        "intents": db.query("SELECT COUNT(*) as count FROM intents")[0]["count"],
        "trades": db.query("SELECT COUNT(*) as count FROM trades")[0]["count"],
    }
    body = "<ul>" + "".join(f"<li>{k}: {v}</li>" for k, v in counts.items()) + "</ul>"
    return render_template_string(TABLE_TEMPLATE, title="Trading Lab Overview", body=body)


@trading_lab_bp.route("/bots")
def bots() -> str:
    search = request.args.get("q")
    rows = _query_rows("bots", search=search)
    return _render_table("Bots", rows, search)


@trading_lab_bp.route("/signals")
def signals() -> str:
    search = request.args.get("q")
    rows = _query_rows("signals", search=search)
    return _render_table("Signals", rows, search)


@trading_lab_bp.route("/trades")
def trades() -> str:
    search = request.args.get("q")
    rows = _query_rows("trades", search=search)
    return _render_table("Trades", rows, search)


@trading_lab_bp.route("/patterns")
def patterns() -> str:
    rows = _query_rows("pattern_registry")
    return _render_table("Patterns", rows)


@trading_lab_bp.route("/strategies")
def strategies() -> str:
    rows = _query_rows("strategy_registry")
    return _render_table("Strategies", rows)


@trading_lab_bp.route("/content-queue")
def content_queue() -> str:
    items: List[str] = []
    for path in sorted(queue_dir().rglob("*.json"))[-200:]:
        items.append(f"<li>{path}</li>")
    body = "<ul>" + "".join(items) + "</ul>" if items else "<p>No content queue items.</p>"
    return render_template_string(TABLE_TEMPLATE, title="Content Queue", body=body)


@trading_lab_bp.route("/devlog")
def devlog() -> str:
    rows = _query_rows("devlog_events")
    return _render_table("Devlog", rows)
