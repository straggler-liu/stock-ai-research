from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _inc_nested(bucket: dict, key1: str, key2: str) -> None:
    if key1 not in bucket:
        bucket[key1] = {}
    bucket[key1][key2] = bucket[key1].get(key2, 0) + 1


def _week_key(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except Exception:
        return "UNKNOWN"


def _day_key(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        return "UNKNOWN"


def generate_execution_quality_report(events_log: str, out_json: str) -> dict:
    path = Path(events_log)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        payload = {
            "events": 0,
            "status_count": {},
            "by_symbol": {},
            "by_env": {},
            "by_day": {},
            "by_week": {},
            "total_filled_quantity": 0.0,
            "total_canceled_quantity": 0.0,
            "reject_count": 0,
        }
        Path(out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    status_count: dict[str, int] = {}
    by_symbol: dict[str, dict[str, int]] = {}
    by_env: dict[str, dict[str, int]] = {}
    by_day: dict[str, dict[str, int]] = {}
    by_week: dict[str, dict[str, int]] = {}
    total_filled_quantity = 0.0
    total_canceled_quantity = 0.0

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        row = json.loads(line)
        status = row.get("status", "UNKNOWN")
        status_count[status] = status_count.get(status, 0) + 1

        payload = row.get("payload", {})
        symbol = payload.get("symbol", "UNKNOWN")
        env = payload.get("env", "UNKNOWN")
        _inc_nested(by_symbol, symbol, status)
        _inc_nested(by_env, env, status)

        ts = row.get("ts", "")
        _inc_nested(by_day, _day_key(ts), status)
        _inc_nested(by_week, _week_key(ts), status)

        if status in {"FILLED", "PARTIAL_FILLED"}:
            total_filled_quantity += float(payload.get("quantity", payload.get("filled_quantity", 0.0)))
        if status == "CANCELED":
            total_canceled_quantity += float(payload.get("canceled_quantity", 0.0))

    result = {
        "events": len(lines),
        "status_count": status_count,
        "by_symbol": by_symbol,
        "by_env": by_env,
        "by_day": by_day,
        "by_week": by_week,
        "total_filled_quantity": round(total_filled_quantity, 4),
        "total_canceled_quantity": round(total_canceled_quantity, 4),
        "reject_count": status_count.get("REJECTED", 0),
    }
    Path(out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
