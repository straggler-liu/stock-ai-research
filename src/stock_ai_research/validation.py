from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .backtest import BacktestReport


@dataclass
class GateResult:
    passed: bool
    failures: list[str]


def load_gate_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_performance_gate(report: BacktestReport, gate: dict) -> GateResult:
    failures: list[str] = []

    if report.total_return_pct < gate["min_total_return_pct"]:
        failures.append(f"total_return_pct<{gate['min_total_return_pct']}")

    if report.max_drawdown_pct > gate["max_drawdown_pct"]:
        failures.append(f"max_drawdown_pct>{gate['max_drawdown_pct']}")

    if report.calmar < gate["min_calmar"]:
        failures.append(f"calmar<{gate['min_calmar']}")

    if report.win_rate_pct < gate["min_win_rate_pct"]:
        failures.append(f"win_rate_pct<{gate['min_win_rate_pct']}")

    if "min_trades" in gate and report.trades < gate["min_trades"]:
        failures.append(f"trades<{gate['min_trades']}")

    if "min_profit_loss_ratio" in gate and report.profit_loss_ratio < gate["min_profit_loss_ratio"]:
        failures.append(f"profit_loss_ratio<{gate['min_profit_loss_ratio']}")

    if "max_consecutive_losses" in gate and report.max_consecutive_losses > gate["max_consecutive_losses"]:
        failures.append(f"max_consecutive_losses>{gate['max_consecutive_losses']}")

    return GateResult(passed=not failures, failures=failures)
