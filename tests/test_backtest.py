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


def test_backtest_uses_long_csv():
    import csv as csv_mod
    from pathlib import Path

    rows = list(
        csv_mod.DictReader(
            Path("data/sample_history_qdii.csv").read_text(encoding="utf-8").splitlines()
        )
    )
    assert len(rows) >= 500


def test_a_stock_csv_exists():
    import csv as csv_mod
    from pathlib import Path

    p = Path("data/sample_history_a_stock.csv")
    assert p.exists()
    rows = list(csv_mod.DictReader(p.read_text(encoding="utf-8").splitlines()))
    assert len(rows) >= 500


def test_backtest_report_has_cost_fields(tmp_path):
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "date,price,benchmark_price,premium_pct,pnl_pct\n"
        "2023-01-03,3.10,100,-0.5,0\n"
        "2023-01-04,3.18,101,0.2,2.58\n"
        "2023-01-05,3.25,102,1.8,4.83\n"
        "2023-01-06,3.30,102.5,3.5,6.45\n"
        "2023-01-07,3.27,102,2.0,5.48\n"
        "2023-01-08,3.35,103,11.2,8.06\n"
        "2023-01-09,3.28,102.8,6.1,5.81\n",
        encoding="utf-8",
    )
    report = run_simple_backtest(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        csv_path=str(csv_path),
    )
    assert isinstance(report.total_cost_pct, float)
    assert report.total_cost_pct >= 0
    assert isinstance(report.profit_loss_ratio, float)
    assert isinstance(report.max_consecutive_losses, int)


def test_backtest_costs_nonzero_when_trades_occur(tmp_path):
    csv_path = tmp_path / "astock.csv"
    csv_path.write_text(
        "date,price,benchmark_price,premium_pct,pnl_pct,ma20_pct,rsi14\n"
        "2023-01-03,10.0,100,0,0,-5.0,25\n"
        "2023-01-04,10.5,101,0,5,1.0,50\n"
        "2023-01-05,10.8,102,0,8,1.5,55\n"
        "2023-01-06,11.0,103,0,10,2.0,60\n"
        "2023-01-07,9.0,95,0,-16.0,1.0,45\n"
        "2023-01-08,8.0,90,0,-20,0,40\n",
        encoding="utf-8",
    )
    report = run_simple_backtest(
        symbol="600519",
        instrument_type=InstrumentType.A_STOCK,
        csv_path=str(csv_path),
    )
    # 有交易时成本必须大于零
    if report.trades > 0:
        assert report.total_cost_pct > 0


def test_max_position_pct_reduces_exposure(tmp_path):
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "date,price,benchmark_price,premium_pct,pnl_pct\n"
        "2023-01-03,3.10,100,-0.5,0\n"
        "2023-01-04,3.18,101,0.2,2.58\n"
        "2023-01-05,3.35,103,11.2,8.06\n"
        "2023-01-06,3.28,102.8,6.1,5.81\n",
        encoding="utf-8",
    )
    report_full = run_simple_backtest(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        csv_path=str(csv_path),
        max_position_pct=1.0,
    )
    report_half = run_simple_backtest(
        symbol="513310",
        instrument_type=InstrumentType.QDII_ETF,
        csv_path=str(csv_path),
        max_position_pct=0.5,
    )
    # 半仓时总成本（绝对值）应小于等于满仓
    assert report_half.total_cost_pct <= report_full.total_cost_pct + 0.001
