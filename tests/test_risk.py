from stock_ai_research.models import InstrumentType, TradeOrder
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


def test_risk_check_skips_premium_for_a_stock():
    """A股高溢价字段（如港股打新溢价）不应触发 ETF 的 premium 检查。"""
    order = TradeOrder(symbol="600519", side="BUY", quantity=1, price=1530.0)
    result = pretrade_risk_check(
        order=order,
        latest_fields={"price": 1530.0, "premium_pct": 15.0},
        account_total_value=200000,
        existing_position_value=0,
        max_position_ratio=0.15,
        instrument_type=InstrumentType.A_STOCK,
    )
    assert result.passed
    assert "premium_over_10_no_buy" not in result.reasons


def test_risk_check_skips_premium_for_us_stock():
    """美股不应触发 ETF premium 检查。"""
    order = TradeOrder(symbol="AAPL", side="BUY", quantity=10, price=185.0)
    result = pretrade_risk_check(
        order=order,
        latest_fields={"price": 185.0, "premium_pct": 20.0},
        account_total_value=500000,
        existing_position_value=0,
        max_position_ratio=0.15,
        instrument_type=InstrumentType.US_STOCK,
    )
    assert result.passed
    assert "premium_over_10_no_buy" not in result.reasons

