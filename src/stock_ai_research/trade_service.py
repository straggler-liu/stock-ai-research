from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .execution import build_broker
from .models import Environment, Fill, OrderEvent, OrderStatus, TradeOrder


class TradeService:
    def __init__(
        self,
        *,
        idempotency_db: str = "data/idempotency.json",
        orders_db: str = "data/orders.json",
        events_log: str = "data/trade_events.jsonl",
    ) -> None:
        self.idempotency_db = Path(idempotency_db)
        self.orders_db = Path(orders_db)
        self.events_log = Path(events_log)
        self.idempotency_db.parent.mkdir(parents=True, exist_ok=True)
        self.events_log.parent.mkdir(parents=True, exist_ok=True)
        if not self.idempotency_db.exists():
            self.idempotency_db.write_text("{}", encoding="utf-8")
        if not self.orders_db.exists():
            self.orders_db.write_text("{}", encoding="utf-8")

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_event(self, event: OrderEvent) -> None:
        row = asdict(event)
        row["status"] = event.status.value
        row["ts"] = datetime.now(timezone.utc).isoformat()
        with self.events_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _update_order(self, order_id: str, **kwargs) -> None:
        orders = self._load_json(self.orders_db)
        if order_id in orders:
            orders[order_id].update(kwargs)
            self._save_json(self.orders_db, orders)

    def get_order(self, order_id: str) -> dict | None:
        orders = self._load_json(self.orders_db)
        return orders.get(order_id)

    def cancel_order(self, order_id: str) -> dict:
        order = self.get_order(order_id)
        if not order:
            return {"ok": False, "reason": "order_not_found", "order_id": order_id}
        if order["status"] == OrderStatus.FILLED.value:
            return {"ok": False, "reason": "already_filled", "order_id": order_id}
        if order["status"] == OrderStatus.CANCELED.value:
            return {"ok": False, "reason": "already_canceled", "order_id": order_id}

        filled_qty = float(order.get("filled_quantity", 0.0))
        total_qty = float(order.get("quantity", 0.0))
        remaining_qty = max(total_qty - filled_qty, 0.0)

        self._update_order(
            order_id,
            status=OrderStatus.CANCELED.value,
            canceled_quantity=remaining_qty,
        )
        self._append_event(
            OrderEvent(
                order_id=order_id,
                status=OrderStatus.CANCELED,
                payload={
                    "source": "cancel_api",
                    "symbol": order.get("symbol", "UNKNOWN"),
                    "env": order.get("env", "UNKNOWN"),
                    "filled_quantity": filled_qty,
                    "canceled_quantity": remaining_qty,
                },
            )
        )
        return {
            "ok": True,
            "order_id": order_id,
            "status": OrderStatus.CANCELED.value,
            "filled_quantity": filled_qty,
            "canceled_quantity": remaining_qty,
        }

    def complete_order(self, order_id: str) -> dict:
        order = self.get_order(order_id)
        if not order:
            return {"ok": False, "reason": "order_not_found", "order_id": order_id}
        if order["status"] != OrderStatus.PARTIAL_FILLED.value:
            return {"ok": False, "reason": "not_partial_filled", "order_id": order_id}

        remaining_qty = max(order.get("quantity", 0.0) - order.get("filled_quantity", 0.0), 0.0)
        new_filled = order.get("filled_quantity", 0.0) + remaining_qty
        self._update_order(order_id, status=OrderStatus.FILLED.value, filled_quantity=new_filled)
        self._append_event(
            OrderEvent(
                order_id=order_id,
                status=OrderStatus.FILLED,
                payload={"filled_quantity": new_filled, "remaining_filled": remaining_qty},
            )
        )
        return {"ok": True, "order_id": order_id, "status": OrderStatus.FILLED.value}

    def submit_order(
        self,
        *,
        env: Environment,
        order: TradeOrder,
        idempotency_key: str,
        confirm_token: str | None = None,
        risk_token: str | None = None,
    ) -> tuple[str, Fill]:
        idem = self._load_json(self.idempotency_db)
        orders = self._load_json(self.orders_db)
        if idempotency_key in idem:
            order_id = idem[idempotency_key]["order_id"]
            payload = idem[idempotency_key]["fill"]
            fill = Fill(
                symbol=payload["symbol"],
                side=payload["side"],
                quantity=payload["quantity"],
                price=payload["price"],
                env=Environment(payload["env"]),
            )
            return order_id, fill

        order_id = uuid.uuid4().hex[:16]
        orders[order_id] = {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "filled_quantity": 0.0,
            "price": order.price,
            "env": env.value,
            "status": OrderStatus.SUBMITTED.value,
        }
        self._save_json(self.orders_db, orders)
        submit_payload = asdict(order)
        submit_payload["env"] = env.value
        self._append_event(OrderEvent(order_id=order_id, status=OrderStatus.SUBMITTED, payload=submit_payload))

        broker = build_broker(env, confirm_token=confirm_token, risk_token=risk_token)
        raw_fill = broker.place_order(order)

        # paper mode partial-fill simulation for large orders
        if env == Environment.PAPER and order.quantity > 50:
            partial_qty = round(order.quantity * 0.5, 4)
            fill = Fill(
                symbol=raw_fill.symbol,
                side=raw_fill.side,
                quantity=partial_qty,
                price=raw_fill.price,
                env=raw_fill.env,
            )
            self._update_order(order_id, status=OrderStatus.PARTIAL_FILLED.value, filled_quantity=partial_qty)
            event_status = OrderStatus.PARTIAL_FILLED
        else:
            fill = raw_fill
            self._update_order(order_id, status=OrderStatus.FILLED.value, filled_quantity=order.quantity)
            event_status = OrderStatus.FILLED

        fill_payload = asdict(fill)
        fill_payload["env"] = fill.env.value
        self._append_event(OrderEvent(order_id=order_id, status=event_status, payload=fill_payload))

        idem[idempotency_key] = {
            "order_id": order_id,
            "fill": fill_payload,
        }
        self._save_json(self.idempotency_db, idem)
        return order_id, fill
