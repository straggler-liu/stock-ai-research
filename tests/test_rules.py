from stock_ai_research.models import InstrumentType, MarketSnapshot
from stock_ai_research.rules import default_rules, evaluate_rules


def test_l1_qdii_premium_kill():
    snapshot = MarketSnapshot(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        fields={"premium_pct": 14.0, "pnl_pct": 2.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "FORCE_SELL_ALL"
    assert "R_QDII_PREMIUM_13" in decision.triggered_rule_ids


def test_hold_when_no_rule_triggered():
    snapshot = MarketSnapshot(
        symbol="510300",
        instrument_type=InstrumentType.CN_ETF,
        fields={"premium_pct": 0.2, "pnl_pct": 1.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "HOLD"
    assert decision.status == "🟢"


def test_a_stock_ma20_dip_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        fields={"ma20_pct": -5.0, "rsi14": 35.0, "pnl_pct": -5.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_A_STOCK_MA20_DIP" in decision.triggered_rule_ids


def test_a_stock_rsi_oversold_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        fields={"ma20_pct": 1.0, "rsi14": 25.0, "pnl_pct": -3.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_A_STOCK_RSI_OVERSOLD" in decision.triggered_rule_ids


def test_a_stock_no_signal_when_neutral():
    snapshot = MarketSnapshot(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        fields={"ma20_pct": 1.5, "rsi14": 55.0, "pnl_pct": 2.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "HOLD"


def test_hk_stock_week52_low_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="00700",
        instrument_type=InstrumentType.HK_STOCK,
        fields={"week52_low_pct": 5.0, "pnl_pct": -2.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_HK_STOCK_WEEK52_LOW" in decision.triggered_rule_ids


def test_fund_pb_low_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="000001",
        instrument_type=InstrumentType.FUND,
        fields={"pb_ratio": 0.85, "pnl_pct": -1.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_FUND_PB_LOW" in decision.triggered_rule_ids


def test_stop_loss_overrides_watch_buy_signal():
    snapshot = MarketSnapshot(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        fields={"ma20_pct": -5.0, "rsi14": 25.0, "pnl_pct": -16.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "FORCE_SELL_ALL"


def test_us_stock_rsi_oversold_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="AAPL",
        instrument_type=InstrumentType.US_STOCK,
        fields={"rsi14": 25.0, "pnl_pct": -3.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_US_STOCK_RSI_OVERSOLD" in decision.triggered_rule_ids


def test_us_stock_drawdown_bounce_triggers_watch_buy():
    snapshot = MarketSnapshot(
        symbol="MSFT",
        instrument_type=InstrumentType.US_STOCK,
        fields={"day_drawdown_pct": -6.5, "pnl_pct": -8.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "WATCH_BUY"
    assert "R_US_STOCK_DRAWDOWN_BOUNCE" in decision.triggered_rule_ids


def test_a_stock_rsi_overbought_exits_position():
    snapshot = MarketSnapshot(
        symbol="000001",
        instrument_type=InstrumentType.A_STOCK,
        fields={"rsi14": 75.0, "pnl_pct": 5.0, "ma20_pct": 2.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "NO_BUY"
    assert "R_A_STOCK_RSI_OVERBOUGHT" in decision.triggered_rule_ids


def test_qdii_premium_zero_triggers_exit():
    snapshot = MarketSnapshot(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        fields={"premium_pct": 1.5, "pnl_pct": 2.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "NO_BUY"
    assert "R_QDII_PREMIUM_ZERO_EXIT" in decision.triggered_rule_ids


def test_qdii_entry_requires_deep_discount():
    # premium = -1.0% 不够深，不触发买入
    snapshot = MarketSnapshot(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        fields={"premium_pct": -1.0, "pnl_pct": 0.5, "ma20_pct": 1.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "HOLD"


def test_qdii_entry_blocked_in_downtrend():
    # discount 够深但价格在强下跌趋势（ma20<-5%）→ 不触发 R_DISCOUNT_OPPORTUNITY
    snapshot = MarketSnapshot(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        fields={"premium_pct": -2.0, "pnl_pct": -3.0, "ma20_pct": -6.0, "rsi14": 40.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert "R_DISCOUNT_OPPORTUNITY" not in (decision.triggered_rule_ids or [])


def test_trend_stop_triggers_force_sell():
    snapshot = MarketSnapshot(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        fields={"ma20_pct": -6.0, "rsi14": 38.0, "pnl_pct": -8.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "FORCE_SELL_ALL"
    assert "R_TREND_STOP_MA20" in decision.triggered_rule_ids


def test_hk_stock_rsi_overbought_exits():
    snapshot = MarketSnapshot(
        symbol="00700",
        instrument_type=InstrumentType.HK_STOCK,
        fields={"rsi14": 75.0, "week52_low_pct": 25.0, "pnl_pct": 8.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "NO_BUY"
    assert "R_HK_STOCK_RSI_OVERBOUGHT" in decision.triggered_rule_ids


def test_us_stock_rsi_overbought_exits():
    snapshot = MarketSnapshot(
        symbol="AAPL",
        instrument_type=InstrumentType.US_STOCK,
        fields={"rsi14": 78.0, "pnl_pct": 10.0},
    )
    decision = evaluate_rules(snapshot, default_rules())
    assert decision.action == "NO_BUY"
    assert "R_US_STOCK_RSI_OVERBOUGHT" in decision.triggered_rule_ids

