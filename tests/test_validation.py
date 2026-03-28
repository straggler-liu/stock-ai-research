from stock_ai_research.backtest import BacktestReport
from stock_ai_research.validation import evaluate_performance_gate


def test_gate_pass():
    report = BacktestReport(
        symbol="513310",
        trades=10,
        total_return_pct=12,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=15,
        calmar=1.5,
        benchmark_return_pct=5,
        alpha_pct=7,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
    }
    result = evaluate_performance_gate(report, gate)
    assert result.passed


def test_gate_fail():
    report = BacktestReport(
        symbol="513310",
        trades=2,
        total_return_pct=2,
        max_drawdown_pct=20,
        win_rate_pct=40,
        cagr_pct=3,
        calmar=0.2,
        benchmark_return_pct=5,
        alpha_pct=-3,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
    }
    result = evaluate_performance_gate(report, gate)
    assert not result.passed
    assert len(result.failures) >= 3
