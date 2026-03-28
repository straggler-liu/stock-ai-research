from pathlib import Path

import pytest

from stock_ai_research.execution import LiveBroker, PaperBroker
from stock_ai_research.models import TradeOrder


def test_paper_broker_buy_and_sell(tmp_path: Path):
    ledger = tmp_path / "paper_ledger.json"
    broker = PaperBroker(str(ledger))

    fill_buy = broker.place_order(TradeOrder(symbol="513310", side="BUY", quantity=100, price=3.2))
    assert fill_buy.env.value == "paper"

    positions = broker.get_positions()
    assert positions[0].quantity == 100

    fill_sell = broker.place_order(TradeOrder(symbol="513310", side="SELL", quantity=40, price=3.4))
    assert fill_sell.quantity == 40
    assert broker.get_positions()[0].quantity == 60


def test_live_requires_dual_tokens():
    with pytest.raises(ValueError):
        LiveBroker(confirm_token=None, risk_token="RISK_OK")
    with pytest.raises(ValueError):
        LiveBroker(confirm_token="LIVE_OK", risk_token=None)
