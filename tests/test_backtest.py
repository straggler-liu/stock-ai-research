from stock_ai_research.backtest import run_simple_backtest
from stock_ai_research.models import InstrumentType


def test_run_simple_backtest():
    report = run_simple_backtest(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        csv_path="data/sample_history_qdii.csv",
    )
    assert report.symbol == "513310"
    assert report.trades >= 1
    assert isinstance(report.total_return_pct, float)
    assert isinstance(report.calmar, float)
    assert isinstance(report.alpha_pct, float)


def test_sample_backtest_meets_return_gate():
    report = run_simple_backtest(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        csv_path="data/sample_history_qdii.csv",
    )
    assert report.total_return_pct >= 5.0
