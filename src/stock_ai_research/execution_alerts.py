from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .notifier import send_feishu_webhook
from .errors import LIVE_GATE_PAUSED


DEFAULT_THRESHOLDS = {
    "max_reject_ratio": 1.0,
    "max_cancel_ratio": 1.0,
    "min_events": 0,
}


DEFAULT_WINDOWS = {
    "7d": {"days": 7, "max_reject_ratio": 1.0, "max_cancel_ratio": 1.0, "min_events": 0},
    "30d": {"days": 30, "max_reject_ratio": 1.0, "max_cancel_ratio": 1.0, "min_events": 0},
}


DEFAULT_ACTIONS = {
    "yellow": {"push": False, "pause_live": False},
    "orange": {"push": True, "pause_live": False},
    "red": {"push": True, "pause_live": True},
}


def load_alert_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_threshold(config: dict, *, symbol: str, env: str) -> dict:
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(config.get("default", {}))

    by_env = config.get("by_env", {})
    if env in by_env:
        thresholds.update(by_env[env])

    by_symbol = config.get("by_symbol", {})
    if symbol in by_symbol:
        thresholds.update(by_symbol[symbol])

    return thresholds


def _window_ratios(by_day: dict, days: int) -> tuple[float, float, int]:
    today = date.today()
    total_events = 0
    rejected = 0
    canceled = 0

    for day_key, counts in by_day.items():
        try:
            d = date.fromisoformat(day_key)
        except Exception:
            continue
        age = (today - d).days
        if 0 <= age < days:
            day_events = sum(counts.values())
            total_events += day_events
            rejected += counts.get("REJECTED", 0)
            canceled += counts.get("CANCELED", 0)

    if total_events == 0:
        return 0.0, 0.0, 0
    return rejected / total_events, canceled / total_events, total_events


def classify_alert_level(alerts: list[str]) -> str:
    if not alerts:
        return "green"
    if any(a.startswith("global.") or a.startswith("env.live") for a in alerts):
        return "red"
    if any(a.startswith("window.") or a.startswith("symbol.") for a in alerts):
        return "orange"
    return "yellow"


def evaluate_execution_alerts(report: dict, config: dict) -> dict:
    events = max(int(report.get("events", 0)), 1)
    status_count = report.get("status_count", {})
    by_symbol = report.get("by_symbol", {})
    by_env = report.get("by_env", {})
    by_day = report.get("by_day", {})

    global_threshold = _resolve_threshold(config, symbol="GLOBAL", env="GLOBAL")
    reject_ratio = status_count.get("REJECTED", 0) / events
    cancel_ratio = status_count.get("CANCELED", 0) / events

    alerts: list[str] = []
    if events >= int(global_threshold.get("min_events", 0)):
        if reject_ratio > float(global_threshold.get("max_reject_ratio", 1.0)):
            alerts.append(f"global.reject_ratio_exceeded:{reject_ratio:.2%}")
        if cancel_ratio > float(global_threshold.get("max_cancel_ratio", 1.0)):
            alerts.append(f"global.cancel_ratio_exceeded:{cancel_ratio:.2%}")

    scoped: list[dict] = []
    for env, env_counts in by_env.items():
        env_events = max(sum(env_counts.values()), 1)
        thresholds = _resolve_threshold(config, symbol="GLOBAL", env=env)
        env_reject = env_counts.get("REJECTED", 0) / env_events
        env_cancel = env_counts.get("CANCELED", 0) / env_events
        env_alerts: list[str] = []
        if env_events >= int(thresholds.get("min_events", 0)):
            if env_reject > float(thresholds.get("max_reject_ratio", 1.0)):
                env_alerts.append(f"env.{env}.reject_ratio_exceeded:{env_reject:.2%}")
            if env_cancel > float(thresholds.get("max_cancel_ratio", 1.0)):
                env_alerts.append(f"env.{env}.cancel_ratio_exceeded:{env_cancel:.2%}")
        alerts.extend(env_alerts)
        scoped.append({"scope": f"env:{env}", "events": env_events, "alerts": env_alerts})

    for symbol, sym_counts in by_symbol.items():
        sym_events = max(sum(sym_counts.values()), 1)
        thresholds = _resolve_threshold(config, symbol=symbol, env="GLOBAL")
        sym_reject = sym_counts.get("REJECTED", 0) / sym_events
        sym_cancel = sym_counts.get("CANCELED", 0) / sym_events
        sym_alerts: list[str] = []
        if sym_events >= int(thresholds.get("min_events", 0)):
            if sym_reject > float(thresholds.get("max_reject_ratio", 1.0)):
                sym_alerts.append(f"symbol.{symbol}.reject_ratio_exceeded:{sym_reject:.2%}")
            if sym_cancel > float(thresholds.get("max_cancel_ratio", 1.0)):
                sym_alerts.append(f"symbol.{symbol}.cancel_ratio_exceeded:{sym_cancel:.2%}")
        alerts.extend(sym_alerts)
        scoped.append({"scope": f"symbol:{symbol}", "events": sym_events, "alerts": sym_alerts})

    window_config = dict(DEFAULT_WINDOWS)
    window_config.update(config.get("windows", {}))
    window_result: dict[str, dict] = {}
    for name, wc in window_config.items():
        days = int(wc.get("days", 0))
        w_reject, w_cancel, w_events = _window_ratios(by_day, days)
        w_alerts: list[str] = []
        if w_events >= int(wc.get("min_events", 0)):
            if w_reject > float(wc.get("max_reject_ratio", 1.0)):
                w_alerts.append(f"window.{name}.reject_ratio_exceeded:{w_reject:.2%}")
            if w_cancel > float(wc.get("max_cancel_ratio", 1.0)):
                w_alerts.append(f"window.{name}.cancel_ratio_exceeded:{w_cancel:.2%}")
        alerts.extend(w_alerts)
        window_result[name] = {
            "days": days,
            "events": w_events,
            "reject_ratio": round(w_reject, 4),
            "cancel_ratio": round(w_cancel, 4),
            "alerts": w_alerts,
        }

    dedup_alerts = sorted(set(alerts))
    level = classify_alert_level(dedup_alerts)
    actions = dict(DEFAULT_ACTIONS)
    actions.update(config.get("actions", {}))
    action = actions.get(level, {"push": False, "pause_live": False})
    block_codes = [LIVE_GATE_PAUSED] if action.get("pause_live", False) else []
    recommended_action = (
        "暂停live并人工复核执行链路" if level == "red" else
        "关注并检查执行参数" if level == "orange" else
        "记录观察"
    )

    return {
        "events": events,
        "reject_ratio": round(reject_ratio, 4),
        "cancel_ratio": round(cancel_ratio, 4),
        "alerts": dedup_alerts,
        "triggered": bool(dedup_alerts),
        "level": level,
        "action": action,
        "block_codes": block_codes,
        "recommended_action": recommended_action,
        "scoped": scoped,
        "windows": window_result,
    }


def build_execution_alert_card(summary: dict) -> dict:
    level_icon = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}
    icon = level_icon.get(summary.get("level", "green"), "🟢")
    lines = "\n".join(f"- {a}" for a in summary["alerts"]) or "- 无"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{icon} 执行质量告警"},
                "template": "red" if summary.get("level") == "red" else "orange" if summary.get("level") == "orange" else "green",
            },
            "elements": [
                {"tag": "markdown", "content": f"events: {summary['events']}"},
                {"tag": "markdown", "content": f"reject_ratio: {summary['reject_ratio']:.2%}"},
                {"tag": "markdown", "content": f"cancel_ratio: {summary['cancel_ratio']:.2%}"},
                {"tag": "markdown", "content": f"level: {summary.get('level', 'green')}"},
                {"tag": "markdown", "content": f"block_codes: {', '.join(summary.get('block_codes', [])) or '无'}"},
                {"tag": "markdown", "content": f"recommended_action: {summary.get('recommended_action', '记录观察')}"},
                {"tag": "markdown", "content": f"alerts:\n{lines}"},
            ],
        },
    }


def maybe_push_execution_alert(summary: dict, webhook_url: str) -> bool:
    if not webhook_url or not summary.get("action", {}).get("push", False):
        return False
    return send_feishu_webhook(build_execution_alert_card(summary), webhook_url)
