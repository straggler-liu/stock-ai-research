from __future__ import annotations

from dataclasses import dataclass

from .models import TradeOrder


@dataclass
class RiskCheckResult:
    passed: bool
    reasons: list[str]


def pretrade_risk_check(
    *,
    order: TradeOrder,
    latest_fields: dict,
    account_total_value: float,
    existing_position_value: float,
    max_position_ratio: float = 0.15,
) -> RiskCheckResult:
    reasons: list[str] = []

    if "price" not in latest_fields:
        reasons.append("missing_price")

    if order.quantity <= 0 or order.price <= 0:
        reasons.append("invalid_order_value")

    order_value = order.quantity * order.price
    new_ratio = (existing_position_value + order_value) / max(account_total_value, 1e-6)
    if new_ratio > max_position_ratio:
        reasons.append("position_limit_exceeded")

    premium = float(latest_fields.get("premium_pct", 0.0))
    if premium > 10:
        reasons.append("premium_over_10_no_buy")

    return RiskCheckResult(passed=not reasons, reasons=reasons)
