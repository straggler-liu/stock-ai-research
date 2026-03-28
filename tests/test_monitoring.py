from stock_ai_research import monitoring


def test_run_watchlist_without_webhook():
    rows = monitoring.run_watchlist("configs/sample_watchlist.json")
    assert len(rows) >= 1
    assert rows[0]["sent"] is False


def test_run_watchlist_with_webhook(monkeypatch):
    monkeypatch.setattr(monitoring, "send_feishu_webhook", lambda payload, webhook_url: True)
    rows = monitoring.run_watchlist("configs/sample_watchlist.json", webhook_url="https://example.com")
    assert all(r["sent"] for r in rows)


def test_run_watchlist_enforce_gate(monkeypatch):
    monkeypatch.setattr(monitoring, "send_feishu_webhook", lambda payload, webhook_url: True)
    rows = monitoring.run_watchlist(
        "configs/sample_watchlist.json",
        webhook_url="https://example.com",
        enforce_gate=True,
        gate_path="configs/performance_gate.json",
    )
    assert rows[0]["gate_passed"] is True
    assert rows[0]["live_allowed"] is True
    assert rows[0]["sent"] is True


def test_run_watchlist_blocked_by_live_gate(monkeypatch):
    monkeypatch.setattr(monitoring, "send_feishu_webhook", lambda payload, webhook_url: True)
    rows = monitoring.run_watchlist(
        "configs/sample_watchlist.json",
        webhook_url="https://example.com",
        live_gate_paused=True,
        live_gate_reason="exec_alert_red",
    )
    assert all(not r["live_allowed"] for r in rows)
    assert all(r["live_block_reason"] == "exec_alert_red" for r in rows)
    assert all(r["live_block_code"] == "LIVE_GATE_PAUSED" for r in rows)
    assert all(r["sent"] is False for r in rows)
