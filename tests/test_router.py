from stock_ai_research.models import InstrumentType
from stock_ai_research.router import detect_instrument_type


def test_detect_qdii_etf():
    assert detect_instrument_type("513310", is_qdii=True) == InstrumentType.QDII_ETF


def test_detect_a_stock():
    assert detect_instrument_type("600519") == InstrumentType.A_STOCK


def test_detect_us_stock():
    assert detect_instrument_type("NVDA") == InstrumentType.US_STOCK
