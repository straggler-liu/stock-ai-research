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


def test_gate_passes_with_new_fields():
    report = BacktestReport(
        symbol="600519",
        trades=15,
        total_return_pct=18,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=20,
        calmar=2.0,
        benchmark_return_pct=8,
        alpha_pct=10,
        total_cost_pct=0.12,
        profit_loss_ratio=1.8,
        max_consecutive_losses=3,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
        "min_trades": 10,
        "min_profit_loss_ratio": 1.5,
        "max_consecutive_losses": 5,
    }
    result = evaluate_performance_gate(report, gate)
    assert result.passed
    assert result.failures == []


def test_gate_fails_min_trades():
    report = BacktestReport(
        symbol="600519",
        trades=3,
        total_return_pct=18,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=20,
        calmar=2.0,
        benchmark_return_pct=8,
        alpha_pct=10,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
        "min_trades": 10,
    }
    result = evaluate_performance_gate(report, gate)
    assert not result.passed
    assert "trades<10" in result.failures


def test_gate_fails_profit_loss_ratio():
    report = BacktestReport(
        symbol="600519",
        trades=15,
        total_return_pct=18,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=20,
        calmar=2.0,
        benchmark_return_pct=8,
        alpha_pct=10,
        profit_loss_ratio=0.8,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
        "min_profit_loss_ratio": 1.5,
    }
    result = evaluate_performance_gate(report, gate)
    assert not result.passed
    assert "profit_loss_ratio<1.5" in result.failures


def test_gate_fails_max_consecutive_losses():
    report = BacktestReport(
        symbol="600519",
        trades=15,
        total_return_pct=18,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=20,
        calmar=2.0,
        benchmark_return_pct=8,
        alpha_pct=10,
        profit_loss_ratio=2.0,
        max_consecutive_losses=8,
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
        "max_consecutive_losses": 5,
    }
    result = evaluate_performance_gate(report, gate)
    assert not result.passed
    assert "max_consecutive_losses>5" in result.failures


def test_gate_new_checks_absent_when_keys_missing():
    report = BacktestReport(
        symbol="513310",
        trades=2,
        total_return_pct=12,
        max_drawdown_pct=8,
        win_rate_pct=60,
        cagr_pct=15,
        calmar=1.5,
        benchmark_return_pct=5,
        alpha_pct=7,
        profit_loss_ratio=0.0,      # 若 key 存在则会失败
        max_consecutive_losses=99,  # 若 key 存在则会失败
    )
    gate = {
        "min_total_return_pct": 5,
        "max_drawdown_pct": 12,
        "min_calmar": 1.0,
        "min_win_rate_pct": 55,
    }
    result = evaluate_performance_gate(report, gate)
    assert result.passed  # 旧格式 gate 不含新 key，新检查不触发
