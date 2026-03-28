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

    return GateResult(passed=not failures, failures=failures)
