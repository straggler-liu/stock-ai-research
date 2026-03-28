from __future__ import annotations

from .feishu_card import build_decision_card
from .models import MarketSnapshot
from .router import detect_instrument_type
from .rules import default_rules, evaluate_rules


def run_once(symbol: str, fields: dict, *, is_qdii: bool = False, is_fund: bool = False) -> tuple[MarketSnapshot, dict]:
    instrument_type = detect_instrument_type(symbol, is_qdii=is_qdii, is_fund=is_fund)
    snapshot = MarketSnapshot(symbol=symbol, instrument_type=instrument_type, fields=fields)
    decision = evaluate_rules(snapshot, default_rules())
    card = build_decision_card(snapshot, decision)
    return snapshot, card
