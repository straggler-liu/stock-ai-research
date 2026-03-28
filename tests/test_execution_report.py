import json
from pathlib import Path

from stock_ai_research.execution_report import generate_execution_quality_report


def test_generate_execution_quality_report(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    out = tmp_path / "exec_report.json"
    events.write_text(
        "\n".join(
            [
                json.dumps({"ts": "2026-03-20T10:00:00+00:00", "status": "SUBMITTED", "payload": {"symbol": "513310", "env": "paper"}}),
                json.dumps({"ts": "2026-03-20T10:05:00+00:00", "status": "PARTIAL_FILLED", "payload": {"symbol": "513310", "env": "paper", "quantity": 50}}),
                json.dumps({"ts": "2026-03-21T11:00:00+00:00", "status": "CANCELED", "payload": {"symbol": "513310", "env": "paper", "canceled_quantity": 50}}),
                json.dumps({"ts": "2026-03-22T12:00:00+00:00", "status": "REJECTED", "payload": {"symbol": "AAPL", "env": "live"}}),
            ]
        ),
        encoding="utf-8",
    )

    result = generate_execution_quality_report(str(events), str(out))
    assert result["events"] == 4
    assert result["status_count"]["PARTIAL_FILLED"] == 1
    assert result["total_filled_quantity"] == 50.0
    assert result["total_canceled_quantity"] == 50.0
    assert result["by_symbol"]["513310"]["CANCELED"] == 1
    assert result["by_env"]["live"]["REJECTED"] == 1
    assert result["by_day"]["2026-03-20"]["SUBMITTED"] == 1
    assert result["by_week"]["2026-W12"]["REJECTED"] == 1
    assert out.exists()
