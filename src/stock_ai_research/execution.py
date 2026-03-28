from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

from .models import Environment, Fill, Position, TradeOrder


class BrokerAdapter(ABC):
    @abstractmethod
    def get_positions(self) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: TradeOrder) -> Fill:
        raise NotImplementedError


class PaperBroker(BrokerAdapter):
    def __init__(self, ledger_path: str = "data/paper_ledger.json") -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self._save({"positions": {}, "fills": []})

    def _load(self) -> dict:
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def _save(self, payload: dict) -> None:
        self.ledger_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_positions(self) -> list[Position]:
        data = self._load()
        return [Position(symbol=s, **payload) for s, payload in data["positions"].items()]

    def place_order(self, order: TradeOrder) -> Fill:
        data = self._load()
        pos = data["positions"].get(order.symbol, {"quantity": 0.0, "avg_cost": 0.0})

        if order.side.upper() == "BUY":
            new_qty = float(pos["quantity"]) + order.quantity
            new_cost = (
                float(pos["avg_cost"]) * float(pos["quantity"]) + order.price * order.quantity
            ) / new_qty
            pos = {"quantity": new_qty, "avg_cost": new_cost}
        elif order.side.upper() == "SELL":
            new_qty = max(0.0, float(pos["quantity"]) - order.quantity)
            pos = {"quantity": new_qty, "avg_cost": float(pos["avg_cost"]) if new_qty > 0 else 0.0}
        else:
            raise ValueError("side must be BUY or SELL")

        data["positions"][order.symbol] = pos
        fill = Fill(
            symbol=order.symbol,
            side=order.side.upper(),
            quantity=order.quantity,
            price=order.price,
            env=Environment.PAPER,
        )
        fill_payload = asdict(fill)
        fill_payload["env"] = fill.env.value
        data["fills"].append(fill_payload)
        self._save(data)
        return fill


class LiveBroker(BrokerAdapter):
    """Mock live broker with dual confirmation guard.

    In production, replace this class with a real broker API adapter.
    """

    def __init__(self, confirm_token: str | None, risk_token: str | None) -> None:
        if not confirm_token:
            raise ValueError("live mode requires confirm token")
        if not risk_token:
            raise ValueError("live mode requires risk token")
        self.confirm_token = confirm_token
        self.risk_token = risk_token

    def get_positions(self) -> list[Position]:
        return []

    def place_order(self, order: TradeOrder) -> Fill:
        return Fill(
            symbol=order.symbol,
            side=order.side.upper(),
            quantity=order.quantity,
            price=order.price,
            env=Environment.LIVE,
        )


def build_broker(
    env: Environment,
    *,
    confirm_token: str | None = None,
    risk_token: str | None = None,
) -> BrokerAdapter:
    if env == Environment.PAPER:
        return PaperBroker()
    return LiveBroker(confirm_token=confirm_token, risk_token=risk_token)
