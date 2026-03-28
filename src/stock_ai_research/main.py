from __future__ import annotations

import argparse
import json

from .backtest import run_simple_backtest
from .errors import LIVE_GATE_PAUSED, RISK_CHECK_FAILED
from .models import Environment, TradeOrder
from .execution_report import generate_execution_quality_report
from .execution_alerts import evaluate_execution_alerts, load_alert_config, maybe_push_execution_alert
from .live_gate import LiveGate
from .monitoring import run_watchlist
from .orchestrator import run_once
from .report import generate_batch_backtest_report
from .risk import pretrade_risk_check
from .router import detect_instrument_type
from .trade_service import TradeService
from .validation import evaluate_performance_gate, load_gate_config


def cmd_decision(args: argparse.Namespace) -> None:
    fields = json.loads(args.fields)
    snapshot, card = run_once(args.symbol, fields, is_qdii=args.is_qdii, is_fund=args.is_fund)
    print(f"symbol={snapshot.symbol} type={snapshot.instrument_type.value}")
    print(json.dumps(card, ensure_ascii=False, indent=2))


def cmd_backtest(args: argparse.Namespace) -> None:
    instrument_type = detect_instrument_type(args.symbol, is_qdii=args.is_qdii, is_fund=args.is_fund)
    report = run_simple_backtest(
        symbol=args.symbol,
        instrument_type=instrument_type,
        csv_path=args.csv,
        initial_cash=args.initial_cash,
    )
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))


def cmd_validate(args: argparse.Namespace) -> None:
    instrument_type = detect_instrument_type(args.symbol, is_qdii=args.is_qdii, is_fund=args.is_fund)
    report = run_simple_backtest(
        symbol=args.symbol,
        instrument_type=instrument_type,
        csv_path=args.csv,
        initial_cash=args.initial_cash,
    )
    gate = load_gate_config(args.gate)
    result = evaluate_performance_gate(report, gate)
    payload = {
        "report": report.__dict__,
        "gate": gate,
        "passed": result.passed,
        "failures": result.failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_trade(args: argparse.Namespace) -> None:
    env = Environment(args.env)
    gate = LiveGate()
    if env == Environment.LIVE and gate.status().get("paused", False):
        raise SystemExit(f"{LIVE_GATE_PAUSED}: Live trading is paused by risk gate. Use live-gate resume first.")

    order = TradeOrder(
        symbol=args.symbol,
        side=args.side,
        quantity=args.quantity,
        price=args.price,
    )

    latest_fields = json.loads(args.latest_fields)
    risk_result = pretrade_risk_check(
        order=order,
        latest_fields=latest_fields,
        account_total_value=args.account_total,
        existing_position_value=args.existing_position,
        max_position_ratio=args.max_position_ratio,
    )
    if not risk_result.passed:
        raise SystemExit(f"{RISK_CHECK_FAILED}: {','.join(risk_result.reasons)}")

    trade_service = TradeService()
    order_id, fill = trade_service.submit_order(
        env=env,
        order=order,
        idempotency_key=args.idempotency_key,
        confirm_token=args.confirm_token,
        risk_token=args.risk_token,
    )
    payload = fill.__dict__.copy()
    payload["env"] = fill.env.value
    payload["risk_check"] = "passed"
    payload["order_id"] = order_id
    payload["idempotency_key"] = args.idempotency_key
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_batch(args: argparse.Namespace) -> None:
    gate = LiveGate().status()
    result = run_watchlist(
        args.config,
        webhook_url=args.webhook,
        enforce_gate=args.enforce_gate,
        gate_path=args.gate,
        initial_cash=args.initial_cash,
        live_gate_paused=gate.get("paused", False),
        live_gate_reason=gate.get("reason", ""),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    payload = generate_batch_backtest_report(args.config, args.out_json, args.out_csv)
    print(json.dumps(payload, ensure_ascii=False, indent=2))



def cmd_order_status(args: argparse.Namespace) -> None:
    service = TradeService()
    order = service.get_order(args.order_id)
    if not order:
        raise SystemExit("order not found")
    print(json.dumps(order, ensure_ascii=False, indent=2))


def cmd_cancel(args: argparse.Namespace) -> None:
    service = TradeService()
    result = service.cancel_order(args.order_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_complete(args: argparse.Namespace) -> None:
    service = TradeService()
    result = service.complete_order(args.order_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_exec_report(args: argparse.Namespace) -> None:
    result = generate_execution_quality_report(args.events_log, args.out_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_exec_alert(args: argparse.Namespace) -> None:
    report = generate_execution_quality_report(args.events_log, args.report_out)
    config = load_alert_config(args.alert_config)
    summary = evaluate_execution_alerts(report, config)
    gate = LiveGate()
    if summary.get("action", {}).get("pause_live", False):
        gate_state = gate.pause("exec_alert_red")
    else:
        gate_state = gate.status()
    pushed = maybe_push_execution_alert(summary, args.webhook)
    summary["pushed"] = pushed
    summary["live_gate"] = gate_state
    print(json.dumps(summary, ensure_ascii=False, indent=2))



def cmd_live_gate(args: argparse.Namespace) -> None:
    gate = LiveGate()
    if args.action == "status":
        result = gate.status()
    elif args.action == "pause":
        result = gate.pause(args.reason)
    else:
        result = gate.resume()
    print(json.dumps(result, ensure_ascii=False, indent=2))

def main() -> None:
    parser = argparse.ArgumentParser(description="全品种投研工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    decision = subparsers.add_parser("decision", help="单次决策")
    decision.add_argument("--symbol", required=True)
    decision.add_argument("--fields", required=True, help="JSON字符串")
    decision.add_argument("--is-qdii", action="store_true")
    decision.add_argument("--is-fund", action="store_true")
    decision.set_defaults(func=cmd_decision)

    backtest = subparsers.add_parser("backtest", help="历史数据回测")
    backtest.add_argument("--symbol", required=True)
    backtest.add_argument("--csv", required=True, help="CSV文件，至少包含price列")
    backtest.add_argument("--initial-cash", type=float, default=100000.0)
    backtest.add_argument("--is-qdii", action="store_true")
    backtest.add_argument("--is-fund", action="store_true")
    backtest.set_defaults(func=cmd_backtest)

    validate = subparsers.add_parser("validate", help="绩效门槛验收")
    validate.add_argument("--symbol", required=True)
    validate.add_argument("--csv", required=True)
    validate.add_argument("--gate", default="configs/performance_gate.json")
    validate.add_argument("--initial-cash", type=float, default=100000.0)
    validate.add_argument("--is-qdii", action="store_true")
    validate.add_argument("--is-fund", action="store_true")
    validate.set_defaults(func=cmd_validate)

    trade = subparsers.add_parser("trade", help="paper/live下单模拟")
    trade.add_argument("--env", choices=["paper", "live"], required=True)
    trade.add_argument("--symbol", required=True)
    trade.add_argument("--side", choices=["BUY", "SELL"], required=True)
    trade.add_argument("--quantity", type=float, required=True)
    trade.add_argument("--price", type=float, required=True)
    trade.add_argument("--latest-fields", default='{"price":1}')
    trade.add_argument("--account-total", type=float, default=100000.0)
    trade.add_argument("--existing-position", type=float, default=0.0)
    trade.add_argument("--max-position-ratio", type=float, default=0.15)
    trade.add_argument("--confirm-token", default="", help="live模式人工确认令牌")
    trade.add_argument("--risk-token", default="", help="live模式风控确认令牌")
    trade.add_argument("--idempotency-key", required=True, help="幂等键，避免重复下单")
    trade.set_defaults(func=cmd_trade)

    batch = subparsers.add_parser("batch", help="批量监控与推送")
    batch.add_argument("--config", required=True, help="watchlist json")
    batch.add_argument("--webhook", default="", help="飞书 webhook (可选)")
    batch.add_argument("--enforce-gate", action="store_true", help="启用绩效门槛后才允许live")
    batch.add_argument("--gate", default="configs/performance_gate.json")
    batch.add_argument("--initial-cash", type=float, default=100000.0)
    batch.set_defaults(func=cmd_batch)

    report = subparsers.add_parser("report", help="批量回测汇总报表导出")
    report.add_argument("--config", required=True)
    report.add_argument("--out-json", default="data/backtest_report.json")
    report.add_argument("--out-csv", default="data/backtest_report.csv")
    report.set_defaults(func=cmd_report)


    order_status = subparsers.add_parser("order-status", help="查询订单状态")
    order_status.add_argument("--order-id", required=True)
    order_status.set_defaults(func=cmd_order_status)

    cancel = subparsers.add_parser("cancel", help="撤单")
    cancel.add_argument("--order-id", required=True)
    cancel.set_defaults(func=cmd_cancel)

    complete = subparsers.add_parser("complete", help="将部分成交订单补齐成交")
    complete.add_argument("--order-id", required=True)
    complete.set_defaults(func=cmd_complete)

    exec_report = subparsers.add_parser("exec-report", help="导出执行质量统计")
    exec_report.add_argument("--events-log", default="data/trade_events.jsonl")
    exec_report.add_argument("--out-json", default="data/execution_quality_report.json")
    exec_report.set_defaults(func=cmd_exec_report)

    exec_alert = subparsers.add_parser("exec-alert", help="执行质量阈值告警")
    exec_alert.add_argument("--events-log", default="data/trade_events.jsonl")
    exec_alert.add_argument("--report-out", default="data/execution_quality_report.json")
    exec_alert.add_argument("--alert-config", default="configs/execution_alerts.json")
    exec_alert.add_argument("--webhook", default="")
    exec_alert.set_defaults(func=cmd_exec_alert)

    live_gate = subparsers.add_parser("live-gate", help="live交易闸门控制")
    live_gate.add_argument("--action", choices=["status", "pause", "resume"], default="status")
    live_gate.add_argument("--reason", default="manual_pause")
    live_gate.set_defaults(func=cmd_live_gate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
