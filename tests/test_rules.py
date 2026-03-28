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
