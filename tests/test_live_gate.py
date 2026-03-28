from pathlib import Path

from stock_ai_research.live_gate import LiveGate


def test_live_gate_pause_resume(tmp_path: Path):
    state_file = tmp_path / "gate.json"
    gate = LiveGate(str(state_file))

    s0 = gate.status()
    assert s0["paused"] is False

    s1 = gate.pause("risk_alert")
    assert s1["paused"] is True
    assert s1["reason"] == "risk_alert"

    s2 = gate.resume()
    assert s2["paused"] is False
