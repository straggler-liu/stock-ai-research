from __future__ import annotations

import re

from .models import InstrumentType


def detect_instrument_type(symbol: str, *, is_qdii: bool = False, is_fund: bool = False) -> InstrumentType:
    code = symbol.strip().upper()

    if re.fullmatch(r"[A-Z]{1,6}", code):
        return InstrumentType.US_STOCK

    if re.fullmatch(r"\d{5}", code):
        return InstrumentType.HK_STOCK

    if not re.fullmatch(r"\d{6}", code):
        return InstrumentType.UNKNOWN

    if code.startswith(("50", "18")):
        return InstrumentType.REITS

    if is_fund:
        return InstrumentType.FUND

    if code.startswith(("51", "15", "56")):
        if is_qdii:
            return InstrumentType.QDII_ETF
        return InstrumentType.CN_ETF

    if code.startswith(("60", "00", "30")):
        return InstrumentType.A_STOCK

    return InstrumentType.UNKNOWN
