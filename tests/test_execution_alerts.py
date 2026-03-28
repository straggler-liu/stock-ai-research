from datetime import date, timedelta

from stock_ai_research.execution_alerts import evaluate_execution_alerts


def test_evaluate_execution_alerts_triggered():
    d0 = date.today().isoformat()
    d1 = (date.today() - timedelta(days=1)).isoformat()

    report = {
        "events": 10,
        "status_count": {
            "REJECTED": 3,
            "CANCELED": 5,
        },
        "by_env": {
            "live": {"REJECTED": 2, "CANCELED": 1, "FILLED": 1},
        },
        "by_symbol": {
            "513310": {"CANCELED": 3, "FILLED": 1},
        },
        "by_day": {
            d0: {"REJECTED": 1, "CANCELED": 2, "FILLED": 1},
            d1: {"REJECTED": 1, "CANCELED": 1, "FILLED": 1},
        },
    }
    config = {
        "default": {"max_reject_ratio": 0.2, "max_cancel_ratio": 0.4, "min_events": 5},
        "by_env": {"live": {"max_reject_ratio": 0.1, "max_cancel_ratio": 0.5, "min_events": 3}},
        "by_symbol": {"513310": {"max_cancel_ratio": 0.5, "min_events": 3}},
        "windows": {"7d": {"days": 7, "max_reject_ratio": 0.2, "max_cancel_ratio": 0.4, "min_events": 3}},
    }
    summary = evaluate_execution_alerts(report, config)
    assert summary["triggered"]
    assert summary["level"] in {"orange", "red"}
    assert "push" in summary["action"]
    assert any(a.startswith("global.") for a in summary["alerts"])
    assert any(a.startswith("env.live") for a in summary["alerts"])
    assert any(a.startswith("symbol.513310") for a in summary["alerts"])
    assert any(a.startswith("window.7d") for a in summary["alerts"])
    assert "recommended_action" in summary


def test_evaluate_execution_alerts_not_triggered_when_low_events():
    d0 = date.today().isoformat()
    report = {
        "events": 2,
        "status_count": {"REJECTED": 1, "CANCELED": 1},
        "by_env": {"live": {"REJECTED": 1}},
        "by_symbol": {"513310": {"REJECTED": 1}},
        "by_day": {d0: {"REJECTED": 1, "CANCELED": 1}},
    }
    config = {
        "default": {"max_reject_ratio": 0.1, "max_cancel_ratio": 0.1, "min_events": 5},
        "by_env": {"live": {"max_reject_ratio": 0.1, "min_events": 5}},
        "by_symbol": {"513310": {"max_reject_ratio": 0.1, "min_events": 5}},
        "windows": {"7d": {"days": 7, "max_reject_ratio": 0.1, "max_cancel_ratio": 0.1, "min_events": 5}},
    }
    summary = evaluate_execution_alerts(report, config)
    assert not summary["triggered"]
    assert summary["level"] == "green"


def test_evaluate_execution_alerts_red_pause_live():
    d0 = date.today().isoformat()
    report = {
        "events": 10,
        "status_count": {"REJECTED": 3, "CANCELED": 1},
        "by_env": {"live": {"REJECTED": 2, "FILLED": 1}},
        "by_symbol": {},
        "by_day": {d0: {"REJECTED": 3, "FILLED": 1}},
    }
    config = {
        "default": {"max_reject_ratio": 0.2, "max_cancel_ratio": 0.9, "min_events": 1},
        "by_env": {"live": {"max_reject_ratio": 0.1, "min_events": 1}},
        "actions": {"red": {"push": True, "pause_live": True}},
    }
    summary = evaluate_execution_alerts(report, config)
    assert summary["level"] == "red"
    assert summary["action"]["pause_live"] is True
    assert "LIVE_GATE_PAUSED" in summary["block_codes"]
