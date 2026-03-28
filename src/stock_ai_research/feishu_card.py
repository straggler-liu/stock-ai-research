from __future__ import annotations

from .models import Decision, MarketSnapshot


def build_decision_card(snapshot: MarketSnapshot, decision: Decision) -> dict:
    metrics = []
    for k in ["price", "premium_pct", "iopv", "pnl_pct"]:
        if k in snapshot.fields:
            metrics.append(f"{k}: {snapshot.fields[k]}")

    reasons = "\n".join(f"- {r}" for r in decision.reasons)

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{decision.status} {snapshot.symbol} 决策卡片"},
                "template": "red" if decision.status == "🔴" else "blue",
            },
            "elements": [
                {"tag": "markdown", "content": f"**动作**: {decision.action}"},
                {"tag": "markdown", "content": f"**触发规则**: {', '.join(decision.triggered_rule_ids) or '无'}"},
                {"tag": "markdown", "content": f"**关键指标**\n" + "\n".join(metrics)},
                {"tag": "markdown", "content": f"**原因**\n{reasons}"},
            ],
        },
    }
