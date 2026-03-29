from __future__ import annotations

from dataclasses import dataclass

from .models import InstrumentType, TradeOrder


@dataclass
class RiskCheckResult:
    passed: bool
    reasons: list[str]


_ETF_TYPES = {InstrumentType.CN_ETF, InstrumentType.QDII_ETF}


def pretrade_risk_check(
    *,
    order: TradeOrder,
    latest_fields: dict,
    account_total_value: float,
    existing_position_value: float,
    max_position_ratio: float = 0.15,
    instrument_type: InstrumentType | None = None,
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

    # Premium check only applies to ETF types; unknown type retains original behavior
    if instrument_type is None or instrument_type in _ETF_TYPES:
        premium = float(latest_fields.get("premium_pct", 0.0))
        if premium > 10:
            reasons.append("premium_over_10_no_buy")

    return RiskCheckResult(passed=not reasons, reasons=reasons)
