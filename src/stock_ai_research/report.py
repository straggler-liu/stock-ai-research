from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import run_simple_backtest
from .router import detect_instrument_type


def generate_batch_backtest_report(config_path: str, out_json: str, out_csv: str) -> dict:
    rows = json.loads(Path(config_path).read_text(encoding="utf-8"))
    reports: list[dict] = []

    for row in rows:
        symbol = row["symbol"]
        history_csv = row.get("history_csv", "")
        if not history_csv:
            continue

        instrument_type = detect_instrument_type(
            symbol,
            is_qdii=row.get("is_qdii", False),
            is_fund=row.get("is_fund", False),
        )
        report = run_simple_backtest(
            symbol=symbol,
            instrument_type=instrument_type,
            csv_path=history_csv,
        )
        reports.append(asdict(report))

    if not reports:
        summary = {
            "count": 0,
            "avg_total_return_pct": 0.0,
            "avg_max_drawdown_pct": 0.0,
            "avg_calmar": 0.0,
        }
    else:
        summary = {
            "count": len(reports),
            "avg_total_return_pct": round(sum(r["total_return_pct"] for r in reports) / len(reports), 2),
            "avg_max_drawdown_pct": round(sum(r["max_drawdown_pct"] for r in reports) / len(reports), 2),
            "avg_calmar": round(sum(r["calmar"] for r in reports) / len(reports), 2),
        }

    payload = {"summary": summary, "reports": reports}
    Path(out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "trades",
                "total_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "cagr_pct",
                "calmar",
                "benchmark_return_pct",
                "alpha_pct",
                "total_cost_pct",
                "profit_loss_ratio",
                "max_consecutive_losses",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        for report in reports:
            writer.writerow(report)

    return payload
