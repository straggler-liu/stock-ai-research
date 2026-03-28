from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import InstrumentType, MarketSnapshot
from .rules import default_rules, evaluate_rules


@dataclass
class BacktestReport:
    symbol: str
    trades: int
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    cagr_pct: float
    calmar: float
    benchmark_return_pct: float
    alpha_pct: float


def _to_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def run_simple_backtest(
    *,
    symbol: str,
    instrument_type: InstrumentType,
    csv_path: str,
    initial_cash: float = 100000.0,
) -> BacktestReport:
    path = Path(csv_path)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    if not rows:
        raise ValueError("empty backtest dataset")

    cash = initial_cash
    quantity = 0.0
    entry_price = 0.0
    peak_value = initial_cash
    max_drawdown = 0.0
    wins = 0
    losses = 0
    trades = 0

    min_bars_remaining_to_open = 2

    for idx, row in enumerate(rows):
        price = float(row["price"])
        fields = {
            "price": price,
            "premium_pct": float(row.get("premium_pct", 0.0)),
            "pnl_pct": float(row.get("pnl_pct", 0.0)),
        }
        snapshot = MarketSnapshot(symbol=symbol, instrument_type=instrument_type, fields=fields)
        decision = evaluate_rules(snapshot, default_rules())

        bars_remaining = len(rows) - idx - 1

        if (
            decision.action == "WATCH_BUY"
            and quantity == 0
            and cash > 0
            and bars_remaining >= min_bars_remaining_to_open
        ):
            quantity = cash / price
            entry_price = price
            cash = 0.0
            trades += 1

        if decision.action in {"FORCE_SELL_ALL", "NO_BUY"} and quantity > 0:
            pnl = (price - entry_price) / entry_price
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
            cash = quantity * price
            quantity = 0.0
            trades += 1

        net_value = cash + quantity * price
        peak_value = max(peak_value, net_value)
        drawdown = (peak_value - net_value) / peak_value if peak_value > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    final_price = float(rows[-1]["price"])
    final_value = cash + quantity * final_price
    total_return = (final_value - initial_cash) / initial_cash

    start_date = _to_date(rows[0]["date"])
    end_date = _to_date(rows[-1]["date"])
    years = max((end_date - start_date).days / 365.0, 1 / 365.0)
    cagr = (final_value / initial_cash) ** (1 / years) - 1

    benchmark_return = 0.0
    if rows[0].get("benchmark_price") and rows[-1].get("benchmark_price"):
        b0 = float(rows[0]["benchmark_price"])
        b1 = float(rows[-1]["benchmark_price"])
        if b0 > 0:
            benchmark_return = (b1 - b0) / b0

    alpha = total_return - benchmark_return
    calmar = cagr / max(max_drawdown, 1e-6)
    closed_trades = wins + losses
    win_rate = (wins / closed_trades) if closed_trades else 0.0

    return BacktestReport(
        symbol=symbol,
        trades=trades,
        total_return_pct=round(total_return * 100, 2),
        max_drawdown_pct=round(max_drawdown * 100, 2),
        win_rate_pct=round(win_rate * 100, 2),
        cagr_pct=round(cagr * 100, 2),
        calmar=round(calmar, 2),
        benchmark_return_pct=round(benchmark_return * 100, 2),
        alpha_pct=round(alpha * 100, 2),
    )
