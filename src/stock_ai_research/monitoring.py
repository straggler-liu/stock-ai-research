from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .backtest import run_simple_backtest
from .execution_alerts import evaluate_execution_alerts, load_alert_config
from .execution_report import generate_execution_quality_report
from .feishu_card import build_morning_brief_card
from .notifier import send_feishu_webhook
from .orchestrator import run_once
from .router import detect_instrument_type
from .validation import evaluate_performance_gate, load_gate_config
from .errors import LIVE_GATE_PAUSED, MISSING_HISTORY_CSV, PERFORMANCE_GATE_FAILED


def run_watchlist(
    config_path: str,
    *,
    webhook_url: str = "",
    enforce_gate: bool = False,
    gate_path: str = "configs/performance_gate.json",
    initial_cash: float = 100000.0,
    live_gate_paused: bool = False,
    live_gate_reason: str = "",
) -> list[dict]:
    rows = json.loads(Path(config_path).read_text(encoding="utf-8"))
    gate = load_gate_config(gate_path) if enforce_gate else None
    results: list[dict] = []

    for row in rows:
        symbol = row["symbol"]
        fields = row.get("fields", {})
        is_qdii = row.get("is_qdii", False)
        is_fund = row.get("is_fund", False)

        snapshot, card = run_once(symbol, fields, is_qdii=is_qdii, is_fund=is_fund)
        result = {
            "symbol": snapshot.symbol,
            "instrument_type": snapshot.instrument_type.value,
            "card": card,
            "sent": False,
            "live_allowed": True,
            "live_block_reason": "",
            "live_block_code": "",
            "gate_passed": None,
            "gate_failures": [],
        }

        if enforce_gate:
            history_csv = row.get("history_csv", "")
            if not history_csv:
                result["live_allowed"] = False
                result["gate_passed"] = False
                result["gate_failures"] = ["missing_history_csv"]
                result["live_block_reason"] = "missing_history_csv"
                result["live_block_code"] = MISSING_HISTORY_CSV
            else:
                instrument_type = detect_instrument_type(symbol, is_qdii=is_qdii, is_fund=is_fund)
                report = run_simple_backtest(
                    symbol=symbol,
                    instrument_type=instrument_type,
                    csv_path=history_csv,
                    initial_cash=initial_cash,
                )
                gate_result = evaluate_performance_gate(report, gate or {})
                result["gate_passed"] = gate_result.passed
                result["gate_failures"] = gate_result.failures
                result["live_allowed"] = gate_result.passed
                result["gate_report"] = report.__dict__
                if not gate_result.passed:
                    result["live_block_reason"] = "performance_gate_failed"
                    result["live_block_code"] = PERFORMANCE_GATE_FAILED

        if live_gate_paused:
            result["live_allowed"] = False
            result["live_block_reason"] = live_gate_reason or "live_gate_paused"
            result["live_block_code"] = LIVE_GATE_PAUSED

        if webhook_url and result["live_allowed"]:
            result["sent"] = send_feishu_webhook(card, webhook_url)

        results.append(result)

    return results


def run_morning_brief(
    config_path: str,
    *,
    webhook_url: str = "",
    enforce_gate: bool = False,
    gate_path: str = "configs/performance_gate.json",
    initial_cash: float = 100000.0,
    market_news: str = "",
    exec_events_log: str = "data/trade_events.jsonl",
    alert_config_path: str = "configs/execution_alerts.json",
) -> dict:
    """Run full morning briefing: decisions + backtest summary + exec alerts + market news."""
    watchlist_results = run_watchlist(
        config_path,
        enforce_gate=enforce_gate,
        gate_path=gate_path,
        initial_cash=initial_cash,
    )

    # ── 聚合 market_summary ────────────────────────────────────────────────
    market_summary: dict[str, int] = {
        "total": len(watchlist_results),
        "force_sell": 0,
        "no_buy": 0,
        "pause_buy": 0,
        "watch_buy": 0,
        "hold": 0,
    }
    _action_key = {
        "FORCE_SELL_ALL": "force_sell",
        "NO_BUY": "no_buy",
        "PAUSE_BUY": "pause_buy",
        "WATCH_BUY": "watch_buy",
        "HOLD": "hold",
    }
    action_items: list[dict] = []

    for r in watchlist_results:
        card = r.get("card", {})
        elements = card.get("card", {}).get("elements", [])
        action = "HOLD"
        reason = ""
        for el in elements:
            content = el.get("content", "")
            if content.startswith("**动作**:"):
                action = content.split(":", 1)[-1].strip()
            if content.startswith("**原因**"):
                reason = content.replace("**原因**\n", "").replace("- ", "").split("\n")[0]
        key = _action_key.get(action, "hold")
        market_summary[key] = market_summary.get(key, 0) + 1
        if action != "HOLD":
            action_items.append({"symbol": r["symbol"], "action": action, "reason": reason})

    # ── 回测绩效摘要（如有 gate_report）────────────────────────────────────
    backtest_summary: dict | None = None
    reports_with_data = [r["gate_report"] for r in watchlist_results if r.get("gate_report")]
    if reports_with_data:
        count = len(reports_with_data)
        backtest_summary = {
            "count": count,
            "avg_total_return_pct": round(
                sum(rpt.get("total_return_pct", 0) for rpt in reports_with_data) / count, 2
            ),
            "avg_max_drawdown_pct": round(
                sum(rpt.get("max_drawdown_pct", 0) for rpt in reports_with_data) / count, 2
            ),
            "avg_calmar": round(
                sum(rpt.get("calmar", 0) for rpt in reports_with_data) / count, 2
            ),
        }

    # ── 执行告警级别 ───────────────────────────────────────────────────────
    exec_alert_level = "green"
    events_log_path = Path(exec_events_log)
    if events_log_path.exists() and events_log_path.stat().st_size > 0:
        try:
            exec_report = generate_execution_quality_report(exec_events_log)
            if Path(alert_config_path).exists():
                alert_cfg = load_alert_config(alert_config_path)
                alert_summary = evaluate_execution_alerts(exec_report, alert_cfg)
                exec_alert_level = alert_summary.get("level", "green")
        except Exception:
            pass

    brief = {
        "date": date.today().isoformat(),
        "market_summary": market_summary,
        "action_items": action_items,
        "exec_alert_level": exec_alert_level,
        "market_news": market_news,
    }
    if backtest_summary is not None:
        brief["backtest_summary"] = backtest_summary

    if webhook_url:
        card = build_morning_brief_card(brief)
        send_feishu_webhook(card, webhook_url)

    return brief

