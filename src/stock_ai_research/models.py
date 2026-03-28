from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InstrumentType(str, Enum):
    A_STOCK = "A_STOCK"
    HK_STOCK = "HK_STOCK"
    US_STOCK = "US_STOCK"
    CN_ETF = "CN_ETF"
    QDII_ETF = "QDII_ETF"
    FUND = "FUND"
    REITS = "REITS"
    UNKNOWN = "UNKNOWN"


class RuleLevel(int, Enum):
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


class Environment(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OrderStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


@dataclass
class MarketSnapshot:
    symbol: str
    instrument_type: InstrumentType
    fields: dict[str, Any]


@dataclass
class RuleResult:
    rule_id: str
    level: RuleLevel
    triggered: bool
    action: str
    reason: str


@dataclass
class Decision:
    symbol: str
    instrument_type: InstrumentType
    status: str
    action: str
    reasons: list[str] = field(default_factory=list)
    triggered_rule_ids: list[str] = field(default_factory=list)
    blocked_by_rule_id: str | None = None


@dataclass
class TradeOrder:
    symbol: str
    side: str
    quantity: float
    price: float


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0


@dataclass
class Fill:
    symbol: str
    side: str
    quantity: float
    price: float
    env: Environment


@dataclass
class OrderEvent:
    order_id: str
    status: OrderStatus
    payload: dict[str, Any]
