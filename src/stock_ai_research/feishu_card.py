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


_LEVEL_ICON = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}
_ACTION_LABEL = {
    "FORCE_SELL_ALL": "🔴清仓",
    "NO_BUY":         "🟠禁买",
    "PAUSE_BUY":      "🟡暂停",
    "WATCH_BUY":      "🔵观察买入",
    "HOLD":           "🟢持有",
}


def build_morning_brief_card(brief: dict) -> dict:
    """构建智能晨报汇总飞书卡片。

    brief 结构::

        {
            "date": "2026-03-28",
            "market_summary": {
                "total": 5, "force_sell": 1, "no_buy": 0,
                "pause_buy": 1, "watch_buy": 2, "hold": 1,
            },
            "action_items": [
                {"symbol": "513310", "action": "FORCE_SELL_ALL", "reason": "..."},
            ],
            "backtest_summary": {  # optional
                "count": 3, "avg_total_return_pct": 8.5,
                "avg_max_drawdown_pct": 2.1, "avg_calmar": 12.3,
            },
            "exec_alert_level": "green",
            "market_news": "今日市场资讯：...",
        }
    """
    ms = brief.get("market_summary", {})
    total = ms.get("total", 0)
    needs_action = total - ms.get("hold", 0)
    date_str = brief.get("date", "")

    alert_level = brief.get("exec_alert_level", "green")
    alert_icon = _LEVEL_ICON.get(alert_level, "🟢")

    # ── 1. 标题区 ──────────────────────────────────────────────────────────
    header_color = "red" if ms.get("force_sell", 0) > 0 else "orange" if needs_action > 0 else "green"
    header_icon = "🔴" if ms.get("force_sell", 0) > 0 else "🟡" if needs_action > 0 else "🟢"

    elements = []

    # ── 2. 市场概览 ────────────────────────────────────────────────────────
    summary_lines = [
        f"📊 **监控标的**: {total} 只  |  **需操作**: {needs_action} 只",
        f"🔴清仓 {ms.get('force_sell', 0)}  🟠禁买 {ms.get('no_buy', 0)}"
        f"  🟡暂停 {ms.get('pause_buy', 0)}  🔵观察 {ms.get('watch_buy', 0)}"
        f"  🟢持有 {ms.get('hold', 0)}",
    ]
    elements.append({"tag": "markdown", "content": "\n".join(summary_lines)})
    elements.append({"tag": "hr"})

    # ── 3. 需要操作的标的 ──────────────────────────────────────────────────
    action_items = brief.get("action_items", [])
    if action_items:
        lines = ["**📋 需要操作的标的**"]
        for item in action_items:
            label = _ACTION_LABEL.get(item["action"], item["action"])
            reason_short = item.get("reason", "")[:40]
            lines.append(f"- **{item['symbol']}** {label}  _{reason_short}_")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})
    else:
        elements.append({"tag": "markdown", "content": "**📋 需要操作的标的**\n- 无，全部持有或观察"})
    elements.append({"tag": "hr"})

    # ── 4. 回测绩效摘要 ────────────────────────────────────────────────────
    bt = brief.get("backtest_summary")
    if bt and bt.get("count", 0) > 0:
        bt_lines = [
            f"**📈 回测绩效摘要**（{bt['count']} 只标的）",
            f"平均收益: **{bt.get('avg_total_return_pct', 0):.2f}%**"
            f"  最大回撤: **{bt.get('avg_max_drawdown_pct', 0):.2f}%**"
            f"  Calmar: **{bt.get('avg_calmar', 0):.2f}**",
        ]
        elements.append({"tag": "markdown", "content": "\n".join(bt_lines)})
        elements.append({"tag": "hr"})

    # ── 5. 执行告警级别 ────────────────────────────────────────────────────
    elements.append({
        "tag": "markdown",
        "content": f"**⚡ 执行质量**: {alert_icon} {alert_level.upper()}",
    })
    elements.append({"tag": "hr"})

    # ── 6. 市场资讯 ────────────────────────────────────────────────────────
    market_news = brief.get("market_news", "").strip()
    if market_news:
        elements.append({
            "tag": "markdown",
            "content": f"**🌐 今日市场资讯**\n{market_news}",
        })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{header_icon} 智能晨报 {date_str}"},
                "template": header_color,
            },
            "elements": elements,
        },
    }

