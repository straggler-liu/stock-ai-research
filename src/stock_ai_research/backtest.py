from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import InstrumentType, MarketSnapshot
from .rules import default_rules, evaluate_rules

# ---------------------------------------------------------------------------
# 硬编码交易成本（fraction，非百分比）
# A股：买 0.03%，卖 0.13%（含印花税）；ETF/QDII：双向 0.015%；其余 0.1%
# ---------------------------------------------------------------------------
_COSTS: dict[InstrumentType, dict[str, float]] = {
    InstrumentType.A_STOCK:  {"buy": 0.0003, "sell": 0.0013},
    InstrumentType.CN_ETF:   {"buy": 0.00015, "sell": 0.00015},
    InstrumentType.QDII_ETF: {"buy": 0.00015, "sell": 0.00015},
    InstrumentType.FUND:     {"buy": 0.001,   "sell": 0.001},
    InstrumentType.REITS:    {"buy": 0.001,   "sell": 0.001},
    InstrumentType.HK_STOCK: {"buy": 0.001,   "sell": 0.001},
    InstrumentType.US_STOCK: {"buy": 0.001,   "sell": 0.001},
    InstrumentType.UNKNOWN:  {"buy": 0.001,   "sell": 0.001},
}
_SLIPPAGE_RATE = 0.0005  # 0.05% 单边


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
    # 新增字段（含默认值，向后兼容）
    total_cost_pct: float = 0.0       # 总交易成本占初始资金的百分比
    profit_loss_ratio: float = 0.0    # 平均盈利/平均亏损（无亏损时=999.0）
    max_consecutive_losses: int = 0   # 最大连续亏损笔数


def _to_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def run_simple_backtest(
    *,
    symbol: str,
    instrument_type: InstrumentType,
    csv_path: str,
    initial_cash: float = 100000.0,
    max_position_pct: float = 1.0,   # 单次最大仓位比例，默认满仓
) -> BacktestReport:
    path = Path(csv_path)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    if not rows:
        raise ValueError("empty backtest dataset")

    cost_rate = _COSTS.get(instrument_type, _COSTS[InstrumentType.UNKNOWN])

    cash = initial_cash
    quantity = 0.0
    entry_price = 0.0
    peak_value = initial_cash
    max_drawdown = 0.0
    wins = 0
    losses = 0
    trades = 0
    total_cost = 0.0
    win_amounts: list[float] = []
    loss_amounts: list[float] = []
    consecutive_losses = 0
    max_consecutive_losses_val = 0

    min_bars_remaining_to_open = 2

    for idx, row in enumerate(rows):
        price = float(row["price"])
        fields: dict[str, Any] = {}
        for k, v in row.items():
            if k in ("date", "benchmark_price"):
                continue
            try:
                fields[k] = float(v)
            except (TypeError, ValueError):
                fields[k] = v
        # Override pnl_pct with actual position P&L from entry price so stop-loss
        # rules fire based on current holding, not cumulative day-1 return.
        if quantity > 0 and entry_price > 0:
            fields["pnl_pct"] = (price - entry_price) / entry_price * 100
        snapshot = MarketSnapshot(symbol=symbol, instrument_type=instrument_type, fields=fields)
        decision = evaluate_rules(snapshot, default_rules())

        bars_remaining = len(rows) - idx - 1

        if (
            decision.action == "WATCH_BUY"
            and quantity == 0
            and cash > 0
            and bars_remaining >= min_bars_remaining_to_open
        ):
            deploy_cash = cash * max_position_pct
            buy_rate = cost_rate["buy"] + _SLIPPAGE_RATE
            effective_buy_price = price * (1 + buy_rate)
            quantity = deploy_cash / effective_buy_price
            entry_price = price
            cash -= deploy_cash
            total_cost += deploy_cash * buy_rate
            trades += 1

        if decision.action in {"FORCE_SELL_ALL", "NO_BUY"} and quantity > 0:
            sell_rate = cost_rate["sell"] + _SLIPPAGE_RATE
            effective_sell_price = price * (1 - sell_rate)
            proceeds = quantity * effective_sell_price
            total_cost += quantity * price * sell_rate
            pnl = (effective_sell_price - entry_price) / entry_price
            if pnl >= 0:
                wins += 1
                win_amounts.append(pnl * 100)
                consecutive_losses = 0
            else:
                losses += 1
                loss_amounts.append(abs(pnl) * 100)
                consecutive_losses += 1
                max_consecutive_losses_val = max(max_consecutive_losses_val, consecutive_losses)
            cash += proceeds
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

    avg_win = sum(win_amounts) / len(win_amounts) if win_amounts else 0.0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0.0
    # 无亏损时设为999.0，避免 inf 序列化问题，且不会触发 min_profit_loss_ratio 门槛
    profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 999.0

    total_cost_pct = total_cost / initial_cash * 100

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
        total_cost_pct=round(total_cost_pct, 4),
        profit_loss_ratio=round(profit_loss_ratio, 2),
        max_consecutive_losses=max_consecutive_losses_val,
    )
