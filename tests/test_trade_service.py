import json
from pathlib import Path

from stock_ai_research.models import Environment, TradeOrder
from stock_ai_research.trade_service import TradeService


def test_trade_service_idempotency(tmp_path: Path):
    idem = tmp_path / "idem.json"
    orders = tmp_path / "orders.json"
    events = tmp_path / "events.jsonl"
    service = TradeService(idempotency_db=str(idem), orders_db=str(orders), events_log=str(events))

    order = TradeOrder(symbol="513310", side="BUY", quantity=10, price=3.1)

    order_id_1, fill_1 = service.submit_order(
        env=Environment.PAPER,
        order=order,
        idempotency_key="k1",
    )
    order_id_2, fill_2 = service.submit_order(
        env=Environment.PAPER,
        order=order,
        idempotency_key="k1",
    )

    assert order_id_1 == order_id_2
    assert fill_1.price == fill_2.price

    lines = events.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payload = [json.loads(line) for line in lines]
    assert payload[0]["status"] == "SUBMITTED"
    assert payload[1]["status"] == "FILLED"


def test_partial_fill_and_complete(tmp_path: Path):
    idem = tmp_path / "idem.json"
    orders = tmp_path / "orders.json"
    events = tmp_path / "events.jsonl"
    service = TradeService(idempotency_db=str(idem), orders_db=str(orders), events_log=str(events))

    order = TradeOrder(symbol="TEST", side="BUY", quantity=100, price=1)
    order_id, fill = service.submit_order(env=Environment.PAPER, order=order, idempotency_key="k2")

    assert fill.quantity == 50
    loaded = service.get_order(order_id)
    assert loaded is not None
    assert loaded["status"] == "PARTIAL_FILLED"

    completed = service.complete_order(order_id)
    assert completed["ok"]
    assert service.get_order(order_id)["status"] == "FILLED"


def test_get_order_and_cancel(tmp_path: Path):
    idem = tmp_path / "idem.json"
    orders = tmp_path / "orders.json"
    events = tmp_path / "events.jsonl"
    service = TradeService(idempotency_db=str(idem), orders_db=str(orders), events_log=str(events))

    order = TradeOrder(symbol="TEST", side="BUY", quantity=40, price=1)
    order_id, _ = service.submit_order(env=Environment.PAPER, order=order, idempotency_key="k3")

    loaded = service.get_order(order_id)
    assert loaded is not None
    assert loaded["status"] == "FILLED"

    canceled = service.cancel_order(order_id)
    assert not canceled["ok"]
    assert canceled["reason"] == "already_filled"


def test_cancel_partial_order_reports_split(tmp_path: Path):
    idem = tmp_path / "idem.json"
    orders = tmp_path / "orders.json"
    events = tmp_path / "events.jsonl"
    service = TradeService(idempotency_db=str(idem), orders_db=str(orders), events_log=str(events))

    order = TradeOrder(symbol="TEST", side="BUY", quantity=120, price=1)
    order_id, _ = service.submit_order(env=Environment.PAPER, order=order, idempotency_key="k4")

    canceled = service.cancel_order(order_id)
    assert canceled["ok"]
    assert canceled["filled_quantity"] == 60
    assert canceled["canceled_quantity"] == 60
    assert service.get_order(order_id)["status"] == "CANCELED"
