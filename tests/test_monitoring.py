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
    # 500+天的真实模拟数据下，gate 结果有明确的 passed/failed 布尔值
    assert isinstance(rows[0]["gate_passed"], bool)
    # 若 gate 失败，live_allowed 应为 False（不允许实盘）
    if not rows[0]["gate_passed"]:
        assert rows[0]["live_allowed"] is False
        assert rows[0]["live_block_code"] == "PERFORMANCE_GATE_FAILED"
    else:
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


def test_run_morning_brief_returns_summary():
    brief = monitoring.run_morning_brief("configs/sample_watchlist.json")
    assert "date" in brief
    assert "market_summary" in brief
    assert "action_items" in brief
    assert "exec_alert_level" in brief
    ms = brief["market_summary"]
    assert ms["total"] >= 1
    assert ms["total"] == (
        ms["force_sell"] + ms["no_buy"] + ms["pause_buy"] + ms["watch_buy"] + ms["hold"]
    )


def test_run_morning_brief_with_market_news():
    brief = monitoring.run_morning_brief(
        "configs/sample_watchlist.json",
        market_news="美联储维持利率不变，市场情绪偏积极。",
    )
    assert brief["market_news"] == "美联储维持利率不变，市场情绪偏积极。"


def test_run_morning_brief_sends_card(monkeypatch):
    sent = []
    monkeypatch.setattr(monitoring, "send_feishu_webhook", lambda payload, url: sent.append(payload) or True)
    monitoring.run_morning_brief(
        "configs/sample_watchlist.json",
        webhook_url="https://example.com",
        market_news="测试资讯",
    )
    assert len(sent) == 1
    card = sent[0]
    assert card["msg_type"] == "interactive"
    assert "智能晨报" in card["card"]["header"]["title"]["content"]

