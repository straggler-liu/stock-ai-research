from __future__ import annotations

import json
from pathlib import Path

from .backtest import run_simple_backtest
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
