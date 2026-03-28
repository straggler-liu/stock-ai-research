from stock_ai_research.models import TradeOrder
from stock_ai_research.risk import pretrade_risk_check


def test_risk_check_pass():
    order = TradeOrder(symbol="513310", side="BUY", quantity=100, price=3.0)
    result = pretrade_risk_check(
        order=order,
        latest_fields={"price": 3.0, "premium_pct": 1.2},
        account_total_value=100000,
        existing_position_value=5000,
        max_position_ratio=0.15,
    )
    assert result.passed


def test_risk_check_fail_on_premium_and_position():
    order = TradeOrder(symbol="513310", side="BUY", quantity=1000, price=20.0)
    result = pretrade_risk_check(
        order=order,
        latest_fields={"price": 20.0, "premium_pct": 12.0},
        account_total_value=100000,
        existing_position_value=10000,
        max_position_ratio=0.15,
    )
    assert not result.passed
    assert "premium_over_10_no_buy" in result.reasons
    assert "position_limit_exceeded" in result.reasons
