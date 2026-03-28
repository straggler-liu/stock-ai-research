from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import Decision, InstrumentType, MarketSnapshot, RuleLevel, RuleResult


Predicate = Callable[[MarketSnapshot], bool]


@dataclass
class Rule:
    rule_id: str
    level: RuleLevel
    action: str
    reason: str
    predicate: Predicate
    only_types: set[InstrumentType] | None = None

    def evaluate(self, snapshot: MarketSnapshot) -> RuleResult:
        if self.only_types and snapshot.instrument_type not in self.only_types:
            return RuleResult(self.rule_id, self.level, False, self.action, self.reason)
        triggered = self.predicate(snapshot)
        return RuleResult(self.rule_id, self.level, triggered, self.action, self.reason)


def _num(snapshot: MarketSnapshot, field: str, default: float = 0.0) -> float:
    value: Any = snapshot.fields.get(field, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_rules() -> list[Rule]:
    return [
        Rule(
            rule_id="R_STOP_LOSS_15",
            level=RuleLevel.L1,
            action="FORCE_SELL_ALL",
            reason="跌幅超过-15%，触发铁律止损。",
            predicate=lambda s: _num(s, "pnl_pct") <= -15,
        ),
        Rule(
            rule_id="R_QDII_PREMIUM_13",
            level=RuleLevel.L1,
            action="FORCE_SELL_ALL",
            reason="QDII ETF溢价超过13%，触发封杀清仓。",
            predicate=lambda s: _num(s, "premium_pct") > 13,
            only_types={InstrumentType.QDII_ETF},
        ),
        Rule(
            rule_id="R_PREMIUM_10",
            level=RuleLevel.L2,
            action="NO_BUY",
            reason="溢价超过10%，禁止买入。",
            predicate=lambda s: _num(s, "premium_pct") > 10,
            only_types={InstrumentType.CN_ETF, InstrumentType.QDII_ETF},
        ),
        Rule(
            rule_id="R_PREMIUM_3",
            level=RuleLevel.L2,
            action="PAUSE_BUY",
            reason="溢价3%-10%，暂停买入。",
            predicate=lambda s: 3 < _num(s, "premium_pct") <= 10,
            only_types={InstrumentType.CN_ETF, InstrumentType.QDII_ETF},
        ),
        Rule(
            rule_id="R_DISCOUNT_OPPORTUNITY",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="出现折价，可关注建仓机会。",
            predicate=lambda s: _num(s, "premium_pct") < 0,
            only_types={InstrumentType.CN_ETF, InstrumentType.QDII_ETF},
        ),
    ]


STATUS_BY_ACTION = {
    "FORCE_SELL_ALL": "🔴",
    "NO_BUY": "🟠",
    "PAUSE_BUY": "🟡",
    "WATCH_BUY": "🔵",
    "HOLD": "🟢",
}


def evaluate_rules(snapshot: MarketSnapshot, rules: list[Rule]) -> Decision:
    results = [rule.evaluate(snapshot) for rule in rules]
    triggered = [r for r in results if r.triggered]

    if not triggered:
        return Decision(
            symbol=snapshot.symbol,
            instrument_type=snapshot.instrument_type,
            status=STATUS_BY_ACTION["HOLD"],
            action="HOLD",
            reasons=["未触发规则，继续观察。"],
        )

    triggered.sort(key=lambda r: r.level)
    winner = triggered[0]
    blocked_by = None
    if len(triggered) > 1 and triggered[1].level > winner.level:
        blocked_by = winner.rule_id

    return Decision(
        symbol=snapshot.symbol,
        instrument_type=snapshot.instrument_type,
        status=STATUS_BY_ACTION.get(winner.action, "🟢"),
        action=winner.action,
        reasons=[r.reason for r in triggered],
        triggered_rule_ids=[r.rule_id for r in triggered],
        blocked_by_rule_id=blocked_by,
    )
