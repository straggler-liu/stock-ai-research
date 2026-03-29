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
        # ── L1 铁律止损（全品种） ──────────────────────────────────────────
        Rule(
            rule_id="R_STOP_LOSS_15",
            level=RuleLevel.L1,
            action="FORCE_SELL_ALL",
            reason="跌幅超过-15%，触发铁律止损。",
            predicate=lambda s: _num(s, "pnl_pct") <= -15,
        ),
        # ── L1 MA20 趋势止损（全品种，含 rsi14 字段时启用）────────────────
        Rule(
            rule_id="R_TREND_STOP_MA20",
            level=RuleLevel.L1,
            action="FORCE_SELL_ALL",
            reason="价格跌破MA20超过-5%且RSI持续弱势，触发趋势止损。",
            predicate=lambda s: "ma20_pct" in s.fields and _num(s, "ma20_pct") < -5 and _num(s, "rsi14", 50) < 45,
        ),
        # ── L1 QDII ETF 溢价封杀 ─────────────────────────────────────────
        Rule(
            rule_id="R_QDII_PREMIUM_13",
            level=RuleLevel.L1,
            action="FORCE_SELL_ALL",
            reason="QDII ETF溢价超过13%，触发封杀清仓。",
            predicate=lambda s: _num(s, "premium_pct") > 13,
            only_types={InstrumentType.QDII_ETF},
        ),
        # ── L2 ETF 溢价风控 ───────────────────────────────────────────────
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
        # ── L2 QDII ETF 折价消失止盈 ──────────────────────────────────────
        Rule(
            rule_id="R_QDII_PREMIUM_ZERO_EXIT",
            level=RuleLevel.L2,
            action="NO_BUY",
            reason="QDII ETF溢价转正（>1%），折价套利窗口关闭，止盈离场。",
            predicate=lambda s: _num(s, "premium_pct") > 1,
            only_types={InstrumentType.CN_ETF, InstrumentType.QDII_ETF},
        ),
        # ── L2 港股 RSI 超买止盈 ──────────────────────────────────────────
        Rule(
            rule_id="R_HK_STOCK_RSI_OVERBOUGHT",
            level=RuleLevel.L2,
            action="NO_BUY",
            reason="港股RSI>70，超买区域，止盈离场暂停建仓。",
            predicate=lambda s: "rsi14" in s.fields and _num(s, "rsi14") > 70,
            only_types={InstrumentType.HK_STOCK},
        ),
        # ── L2 美股 RSI 超买止盈 ──────────────────────────────────────────
        Rule(
            rule_id="R_US_STOCK_RSI_OVERBOUGHT",
            level=RuleLevel.L2,
            action="NO_BUY",
            reason="美股RSI>70，超买区域，止盈离场暂停建仓。",
            predicate=lambda s: "rsi14" in s.fields and _num(s, "rsi14") > 70,
            only_types={InstrumentType.US_STOCK},
        ),
        # ── L2 A股 RSI 超买止盈 ───────────────────────────────────────────
        Rule(
            rule_id="R_A_STOCK_RSI_OVERBOUGHT",
            level=RuleLevel.L2,
            action="NO_BUY",
            reason="A股RSI>70，超买区域，止盈离场暂停建仓。",
            predicate=lambda s: "rsi14" in s.fields and _num(s, "rsi14") > 70,
            only_types={InstrumentType.A_STOCK},
        ),
        # ── L3 ETF 深度折价机会（需均线趋势过滤）────────────────────────────
        Rule(
            rule_id="R_DISCOUNT_OPPORTUNITY",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="折价超过1.5%且价格不处于强下跌趋势，具备安全边际，关注建仓机会。",
            predicate=lambda s: _num(s, "premium_pct") < -1.5 and _num(s, "ma20_pct", 0) > -5,
            only_types={InstrumentType.CN_ETF, InstrumentType.QDII_ETF},
        ),
        # ── L3 A股 MA20 + RSI 超卖共振 ───────────────────────────────────
        Rule(
            rule_id="R_A_STOCK_MA20_DIP",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="A股价格偏离MA20超-3%且RSI<40，关注超跌建仓机会。",
            predicate=lambda s: _num(s, "ma20_pct") < -3 and _num(s, "rsi14", 50) < 40,
            only_types={InstrumentType.A_STOCK},
        ),
        # ── L3 A股 RSI 极度超卖 ───────────────────────────────────────────
        Rule(
            rule_id="R_A_STOCK_RSI_OVERSOLD",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="A股RSI<30，极度超卖，关注反弹买入机会。",
            predicate=lambda s: "rsi14" in s.fields and _num(s, "rsi14", 50) < 30,
            only_types={InstrumentType.A_STOCK},
        ),
        # ── L3 港股 52周低位 ──────────────────────────────────────────────
        Rule(
            rule_id="R_HK_STOCK_WEEK52_LOW",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="港股价格处于52周低位区间（低位上方10%以内），关注底部建仓机会。",
            predicate=lambda s: "week52_low_pct" in s.fields and 0 < _num(s, "week52_low_pct", 100) <= 10,
            only_types={InstrumentType.HK_STOCK},
        ),
        # ── L3 美股 RSI 超卖 ──────────────────────────────────────────────
        Rule(
            rule_id="R_US_STOCK_RSI_OVERSOLD",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="美股RSI<30，超卖区域，关注反弹买入机会。",
            predicate=lambda s: "rsi14" in s.fields and _num(s, "rsi14", 50) < 30,
            only_types={InstrumentType.US_STOCK},
        ),
        # ── L3 美股 单日大跌止跌反弹 ──────────────────────────────────────
        Rule(
            rule_id="R_US_STOCK_DRAWDOWN_BOUNCE",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="美股单日跌幅超5%且总持仓亏损<15%，关注止跌反弹机会。",
            predicate=lambda s: _num(s, "day_drawdown_pct") < -5 and _num(s, "pnl_pct") > -15,
            only_types={InstrumentType.US_STOCK},
        ),
        # ── L3 基金 PB 低估值 ─────────────────────────────────────────────
        Rule(
            rule_id="R_FUND_PB_LOW",
            level=RuleLevel.L3,
            action="WATCH_BUY",
            reason="基金PB<1.0，处于低估值区间，关注建仓机会。",
            predicate=lambda s: "pb_ratio" in s.fields and 0 < _num(s, "pb_ratio", 99) < 1.0,
            only_types={InstrumentType.FUND},
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
