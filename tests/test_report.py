from pathlib import Path

from stock_ai_research.report import generate_batch_backtest_report


def test_generate_batch_backtest_report(tmp_path: Path):
    out_json = tmp_path / "report.json"
    out_csv = tmp_path / "report.csv"

    payload = generate_batch_backtest_report(
        "configs/sample_watchlist.json",
        str(out_json),
        str(out_csv),
    )

    assert payload["summary"]["count"] >= 1
    assert out_json.exists()
    assert out_csv.exists()
