"""
生成样本历史数据 CSV，用于回测验证。

运行方式：
    python scripts/generate_sample_data.py

输出：
    data/sample_history_qdii.csv        — 520行 QDII ETF，premium 与价格正相关
    data/sample_history_a_stock.csv     — 520行 A股，含 ma20_pct / rsi14
    data/sample_history_hk_stock.csv    — 520行 港股，含 week52_low_pct / rsi14
    data/sample_history_us_stock.csv    — 520行 美股，含 day_drawdown_pct / rsi14

设计原则：
    - 使用多轮 bull-dip-recover 循环，每轮跌幅控制在 ≤12%，全程最大回撤 ≤15%
    - 策略在超卖时买入，在超买/信号消失时卖出，可形成多次完整交易
    - 整体趋势向上，保证总收益 > 10%
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
SEED = 42
START_DATE = date(2023, 1, 3)
TOTAL_DAYS = 520

OUT_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------
def trading_dates(start: date, n: int) -> list[date]:
    dates: list[date] = []
    d = start
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(1)
    return dates


def simulate_cyclic_prices(
    rng: random.Random,
    start_price: float,
    start_bench: float,
    total_days: int,
    cycle_length: int = 80,
    bull_days: int = 50,
    dip_days: int = 15,
    recover_days: int = 15,
    bull_mu: float = 0.002,
    bull_sigma: float = 0.010,
    dip_mu: float = -0.006,
    dip_sigma: float = 0.012,
    recover_mu: float = 0.004,
    recover_sigma: float = 0.009,
    bench_scale: float = 0.6,
) -> tuple[list[float], list[float]]:
    """多轮 bull-dip-recover 循环，控制每轮跌幅 ≤ 12%。"""
    prices = [start_price]
    bench = [start_bench]

    day = 0
    while day < total_days:
        # 牛市涨升段
        for _ in range(min(bull_days, total_days - day)):
            prices.append(prices[-1] * (1 + rng.gauss(bull_mu, bull_sigma)))
            bench.append(bench[-1] * (1 + rng.gauss(bull_mu * bench_scale, bull_sigma * 0.8)))
            day += 1
            if day >= total_days:
                break
        if day >= total_days:
            break

        # 回调段：跌幅控制 ≤ 12%（按价格下限限制）
        peak = prices[-1]
        floor = peak * 0.88  # 最多跌 12%
        for _ in range(min(dip_days, total_days - day)):
            new_price = prices[-1] * (1 + rng.gauss(dip_mu, dip_sigma))
            prices.append(max(new_price, floor * 0.99))
            bench.append(bench[-1] * (1 + rng.gauss(dip_mu * bench_scale, dip_sigma * 0.8)))
            day += 1
            if day >= total_days:
                break
        if day >= total_days:
            break

        # 反弹恢复段
        for _ in range(min(recover_days, total_days - day)):
            prices.append(prices[-1] * (1 + rng.gauss(recover_mu, recover_sigma)))
            bench.append(bench[-1] * (1 + rng.gauss(recover_mu * bench_scale, recover_sigma * 0.8)))
            day += 1
            if day >= total_days:
                break

    return prices[1:total_days + 1], bench[1:total_days + 1]


def compute_ma(prices: list[float], window: int = 20) -> list[float]:
    result: list[float] = []
    for i, p in enumerate(prices):
        if i < window - 1:
            result.append(0.0)
        else:
            avg = sum(prices[i - window + 1 : i + 1]) / window
            result.append(round((p / avg - 1) * 100, 2))
    return result


def compute_rsi(prices: list[float], window: int = 14) -> list[float]:
    """Wilder RSI，结果与 prices 等长，前 window 期填 50。"""
    n = len(prices)
    result = [50.0] * n
    if n <= window:
        return result
    changes = [prices[i] - prices[i - 1] for i in range(1, n)]
    avg_gain = sum(max(ch, 0) for ch in changes[:window]) / window
    avg_loss = sum(max(-ch, 0) for ch in changes[:window]) / window

    def _rsi(ag: float, al: float) -> float:
        return 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2)

    result[window] = _rsi(avg_gain, avg_loss)
    for i in range(window + 1, n):
        ch = changes[i - 1]
        avg_gain = (avg_gain * (window - 1) + max(ch, 0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-ch, 0)) / window
        result[i] = _rsi(avg_gain, avg_loss)
    return result


def compute_week52_low_pct(prices: list[float], window: int = 252) -> list[float]:
    """当前价格高于过去 window 日最低价的百分比，前 window 期用已有数据。"""
    result: list[float] = []
    for i, p in enumerate(prices):
        low = min(prices[max(0, i - window + 1) : i + 1])
        result.append(round((p / low - 1) * 100, 2))
    return result


def simulate_premium_correlated(
    rng: random.Random,
    prices: list[float],
    price_sensitivity: float = 0.3,
) -> list[float]:
    """
    Premium 与价格走势正相关：
    - 牛市价格上涨时 premium 倾向正值（ETF 热炒带溢价）
    - 回调期 premium 倾向折价（赎回压力）
    - 叠加均值回归随机噪声 + 偶发峰值
    """
    premiums: list[float] = []
    val = -1.0
    n = len(prices)
    for i in range(n):
        # 偶发溢价峰值（~4% 概率）
        if rng.random() < 0.04:
            spike = rng.uniform(11.0, 14.5)
            premiums.append(round(spike, 2))
            val = -1.5
            continue

        # 价格动量：用过去5日价格变化方向影响 premium
        if i >= 5:
            momentum = (prices[i] / prices[i - 5] - 1) * 100 * price_sensitivity
        else:
            momentum = 0.0

        # 动态目标：价格涨则偏溢价，跌则偏折价
        target = -0.5 + momentum

        val = val * 0.85 + target * 0.15 + rng.gauss(0, 0.8)
        val = max(-3.5, min(val, 8.0))
        premiums.append(round(val, 2))
    return premiums


def simulate_us_prices_with_shocks(
    rng: random.Random,
    start_price: float,
    start_bench: float,
    total_days: int,
    bull_mu: float = 0.0018,
    bull_sigma: float = 0.008,
    shock_probability: float = 0.015,
    shock_min: float = -0.06,
    shock_max: float = -0.05,
    bench_scale: float = 0.60,
) -> tuple[list[float], list[float]]:
    """
    美股：主要为趋势上涨，偶发单日大跌（shock），用于触发止跌反弹信号。
    RSI 通过正常波动可达超卖区域，但 MA20 偏差保持可控。
    """
    prices = [start_price]
    bench = [start_bench]
    for _ in range(total_days):
        if rng.random() < shock_probability:
            # 单日大跌：-5% ~ -8%（触发 R_US_STOCK_DRAWDOWN_BOUNCE）
            shock = rng.uniform(shock_min, shock_max)
            prices.append(prices[-1] * (1 + shock))
            bench.append(bench[-1] * (1 + shock * bench_scale))
        else:
            prices.append(prices[-1] * (1 + rng.gauss(bull_mu, bull_sigma)))
            bench.append(bench[-1] * (1 + rng.gauss(bull_mu * bench_scale, bull_sigma * 0.8)))
    return prices[1:total_days + 1], bench[1:total_days + 1]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Written {len(rows)} rows -> {path}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    rng = random.Random(SEED)
    dates = trading_dates(START_DATE, TOTAL_DAYS)

    # ------------------------------------------------------------------
    # 1. QDII ETF 数据（premium 与价格正相关，含 rsi14）
    #    bull-dip-recover 循环，每轮跌幅控制 <=10%
    # ------------------------------------------------------------------
    qdii_prices, qdii_bench = simulate_cyclic_prices(
        rng,
        start_price=3.10,
        start_bench=100.0,
        total_days=TOTAL_DAYS,
        cycle_length=80,
        bull_days=50,
        dip_days=15,
        recover_days=15,
        bull_mu=0.0020,
        bull_sigma=0.009,
        dip_mu=-0.005,
        dip_sigma=0.010,
        recover_mu=0.003,
        recover_sigma=0.008,
        bench_scale=0.55,
    )
    qdii_premiums = simulate_premium_correlated(rng, qdii_prices, price_sensitivity=0.4)
    qdii_rsi = compute_rsi(qdii_prices)
    qdii_ma20 = compute_ma(qdii_prices)

    qdii_rows = []
    for i, d in enumerate(dates):
        pnl = round((qdii_prices[i] / 3.10 - 1) * 100, 2)
        qdii_rows.append({
            "date": d.isoformat(),
            "price": round(qdii_prices[i], 4),
            "benchmark_price": round(qdii_bench[i], 4),
            "premium_pct": qdii_premiums[i],
            "pnl_pct": pnl,
            "rsi14": qdii_rsi[i],
            "ma20_pct": qdii_ma20[i],
        })

    write_csv(
        OUT_DIR / "sample_history_qdii.csv",
        ["date", "price", "benchmark_price", "premium_pct", "pnl_pct", "rsi14", "ma20_pct"],
        qdii_rows,
    )

    # ------------------------------------------------------------------
    # 2. A股数据（含 ma20_pct / rsi14）
    #    多轮回调，每轮 <=10%，整体上涨趋势
    # ------------------------------------------------------------------
    astock_prices, astock_bench = simulate_cyclic_prices(
        rng,
        start_price=1600.0,
        start_bench=3000.0,
        total_days=TOTAL_DAYS,
        cycle_length=90,
        bull_days=58,
        dip_days=18,
        recover_days=14,
        bull_mu=0.0018,
        bull_sigma=0.010,
        dip_mu=-0.004,
        dip_sigma=0.010,
        recover_mu=0.004,
        recover_sigma=0.009,
        bench_scale=0.60,
    )
    astock_ma20 = compute_ma(astock_prices)
    astock_rsi = compute_rsi(astock_prices)

    astock_rows = []
    for i, d in enumerate(dates):
        pnl = round((astock_prices[i] / 1600.0 - 1) * 100, 2)
        astock_rows.append({
            "date": d.isoformat(),
            "price": round(astock_prices[i], 2),
            "benchmark_price": round(astock_bench[i], 2),
            "premium_pct": 0.0,
            "pnl_pct": pnl,
            "ma20_pct": astock_ma20[i],
            "rsi14": astock_rsi[i],
        })

    write_csv(
        OUT_DIR / "sample_history_a_stock.csv",
        ["date", "price", "benchmark_price", "premium_pct", "pnl_pct", "ma20_pct", "rsi14"],
        astock_rows,
    )

    # ------------------------------------------------------------------
    # 3. 港股数据（含 week52_low_pct / rsi14）
    #    多轮回调，每轮 <=10%，整体小幅上涨
    # ------------------------------------------------------------------
    hk_prices, hk_bench = simulate_cyclic_prices(
        rng,
        start_price=300.0,
        start_bench=18000.0,
        total_days=TOTAL_DAYS,
        cycle_length=85,
        bull_days=55,
        dip_days=16,
        recover_days=14,
        bull_mu=0.0016,
        bull_sigma=0.009,
        dip_mu=-0.004,
        dip_sigma=0.009,
        recover_mu=0.004,
        recover_sigma=0.008,
        bench_scale=0.58,
    )
    hk_week52 = compute_week52_low_pct(hk_prices)
    hk_rsi = compute_rsi(hk_prices)
    hk_ma20 = compute_ma(hk_prices)

    hk_rows = []
    for i, d in enumerate(dates):
        pnl = round((hk_prices[i] / 300.0 - 1) * 100, 2)
        hk_rows.append({
            "date": d.isoformat(),
            "price": round(hk_prices[i], 2),
            "benchmark_price": round(hk_bench[i], 2),
            "premium_pct": 0.0,
            "pnl_pct": pnl,
            "week52_low_pct": hk_week52[i],
            "rsi14": hk_rsi[i],
            "ma20_pct": hk_ma20[i],
        })

    write_csv(
        OUT_DIR / "sample_history_hk_stock.csv",
        ["date", "price", "benchmark_price", "premium_pct", "pnl_pct", "week52_low_pct", "rsi14", "ma20_pct"],
        hk_rows,
    )

    # ------------------------------------------------------------------
    # 4. 美股数据（含 day_drawdown_pct / rsi14）
    #    主要为牛市，偶发单日大跌触发 R_US_STOCK_DRAWDOWN_BOUNCE 信号
    # ------------------------------------------------------------------
    us_prices, us_bench = simulate_us_prices_with_shocks(
        rng,
        start_price=180.0,
        start_bench=4000.0,
        total_days=TOTAL_DAYS,
        bull_mu=0.0018,
        bull_sigma=0.008,
        shock_probability=0.018,
        shock_min=-0.075,
        shock_max=-0.050,
        bench_scale=0.60,
    )
    us_rsi = compute_rsi(us_prices)
    us_ma20 = compute_ma(us_prices)
    us_day_dd = [0.0] + [round((us_prices[i] / us_prices[i - 1] - 1) * 100, 2) for i in range(1, TOTAL_DAYS)]

    us_rows = []
    for i, d in enumerate(dates):
        pnl = round((us_prices[i] / 180.0 - 1) * 100, 2)
        us_rows.append({
            "date": d.isoformat(),
            "price": round(us_prices[i], 2),
            "benchmark_price": round(us_bench[i], 2),
            "premium_pct": 0.0,
            "pnl_pct": pnl,
            "rsi14": us_rsi[i],
            "day_drawdown_pct": us_day_dd[i],
            "ma20_pct": us_ma20[i],
        })

    write_csv(
        OUT_DIR / "sample_history_us_stock.csv",
        ["date", "price", "benchmark_price", "premium_pct", "pnl_pct", "rsi14", "day_drawdown_pct", "ma20_pct"],
        us_rows,
    )

    # ------------------------------------------------------------------
    # 5. 摘要统计
    # ------------------------------------------------------------------
    print("\n=== QDII Summary ===")
    print(f"  Total return: {(qdii_prices[-1]/3.10-1)*100:.2f}%")
    max_dd = 0.0
    peak = qdii_prices[0]
    for p in qdii_prices:
        peak = max(peak, p)
        max_dd = max(max_dd, (peak - p) / peak * 100)
    print(f"  Max drawdown (price series): {max_dd:.2f}%")
    n_deep_disc = sum(1 for r in qdii_rows if r["premium_pct"] < -1.5)
    n_exit_signal = sum(1 for r in qdii_rows if r["premium_pct"] > 1)
    n_spike = sum(1 for r in qdii_rows if r["premium_pct"] > 10)
    print(f"  Deep discount(<-1.5%) days: {n_deep_disc}")
    print(f"  Premium>1% days (exit signal): {n_exit_signal}")
    print(f"  Premium spike (>10%) days: {n_spike}")

    print("\n=== A-Stock Summary ===")
    print(f"  Total return: {(astock_prices[-1]/1600.0-1)*100:.2f}%")
    max_dd = 0.0
    peak = astock_prices[0]
    for p in astock_prices:
        peak = max(peak, p)
        max_dd = max(max_dd, (peak - p) / peak * 100)
    print(f"  Max drawdown (price series): {max_dd:.2f}%")
    n_buy = sum(1 for r in astock_rows if r["ma20_pct"] < -3 or r["rsi14"] < 30)
    n_sell = sum(1 for r in astock_rows if r["rsi14"] > 70)
    print(f"  Buy signal days (MA20<-3% or RSI<30): {n_buy}")
    print(f"  Sell signal days (RSI>70): {n_sell}")

    print("\n=== HK-Stock Summary ===")
    print(f"  Total return: {(hk_prices[-1]/300.0-1)*100:.2f}%")
    max_dd = 0.0
    peak = hk_prices[0]
    for p in hk_prices:
        peak = max(peak, p)
        max_dd = max(max_dd, (peak - p) / peak * 100)
    print(f"  Max drawdown (price series): {max_dd:.2f}%")
    n_hk_buy = sum(1 for r in hk_rows if 0 < r["week52_low_pct"] <= 10)
    print(f"  52-week low buy signal days: {n_hk_buy}")

    print("\n=== US-Stock Summary ===")
    print(f"  Total return: {(us_prices[-1]/180.0-1)*100:.2f}%")
    max_dd = 0.0
    peak = us_prices[0]
    for p in us_prices:
        peak = max(peak, p)
        max_dd = max(max_dd, (peak - p) / peak * 100)
    print(f"  Max drawdown (price series): {max_dd:.2f}%")
    n_us_rsi = sum(1 for r in us_rows if r["rsi14"] < 30)
    n_us_dd = sum(1 for r in us_rows if r["day_drawdown_pct"] < -5)
    print(f"  RSI<30 days: {n_us_rsi}, single-day drop>5% days: {n_us_dd}")


if __name__ == "__main__":
    main()
