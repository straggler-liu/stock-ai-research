"""
股票AI研究平台 — 桌面应用
运行方式：python app.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog
import tkinter as tk
from tkinter import ttk

# ── 设置工作目录，确保相对路径正确 ──────────────────────────────────────────
ROOT = Path(__file__).parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

# ── 路径常量 ─────────────────────────────────────────────────────────────────
WATCHLIST_PATH = "configs/sample_watchlist.json"
GATE_PATH = "configs/performance_gate.json"
EVENTS_LOG = "data/trade_events.jsonl"
APP_SETTINGS_PATH = "configs/app_settings.json"

# ── 动作颜色映射 ──────────────────────────────────────────────────────────────
ACTION_BG = {
    "FORCE_SELL_ALL": "#FFCCCC",
    "NO_BUY":         "#FFE0B2",
    "PAUSE_BUY":      "#FFF9C4",
    "WATCH_BUY":      "#BBDEFB",
    "HOLD":           "#C8E6C9",
}
ACTION_FG = {
    "FORCE_SELL_ALL": "#B71C1C",
    "NO_BUY":         "#E65100",
    "PAUSE_BUY":      "#827717",
    "WATCH_BUY":      "#0D47A1",
    "HOLD":           "#1B5E20",
}
ACTION_LABEL = {
    "FORCE_SELL_ALL": "🔴 立即止损",
    "NO_BUY":         "🟠 禁止买入",
    "PAUSE_BUY":      "🟡 暂停买入",
    "WATCH_BUY":      "🔵 关注建仓",
    "HOLD":           "🟢 继续持有",
}

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: 辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def load_watchlist() -> list[dict]:
    try:
        return json.loads(Path(WATCHLIST_PATH).read_text(encoding="utf-8"))
    except Exception:
        return []


def save_watchlist(data: list[dict]) -> None:
    Path(WATCHLIST_PATH).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_gate_cfg() -> dict:
    try:
        return json.loads(Path(GATE_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {"min_total_return_pct": 5.0, "max_drawdown_pct": 12.0,
                "min_calmar": 1.0, "min_win_rate_pct": 55.0}


def save_gate_cfg(data: dict) -> None:
    Path(GATE_PATH).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_app_settings() -> dict:
    try:
        return json.loads(Path(APP_SETTINGS_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {"webhook_url": ""}


def save_app_settings(data: dict) -> None:
    Path(APP_SETTINGS_PATH).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_trade_events(max_rows: int = 200) -> list[dict]:
    path = Path(EVENTS_LOG)
    if not path.exists():
        return []
    events = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return events[-max_rows:]


def fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"


def fmt_num(val: float | None, digits: int = 2) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: 后台线程 Worker
# ══════════════════════════════════════════════════════════════════════════════

class Worker:
    """将耗时函数放到 daemon 线程执行，结果通过 root.after(0) 安全回传主线程。"""

    def __init__(self, root: tk.Tk):
        self.root = root

    def run(self, fn, args: tuple, on_done, on_error):
        def _target():
            try:
                result = fn(*args)
                self.root.after(0, on_done, result)
            except Exception as e:
                self.root.after(0, on_error, f"{type(e).__name__}: {e}")
        threading.Thread(target=_target, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Tab1 — 监控面板
# ══════════════════════════════════════════════════════════════════════════════

class DashboardTab(ttk.Frame):
    def __init__(self, parent, worker: Worker):
        super().__init__(parent)
        self.worker = worker
        self._results: dict[str, dict] = {}   # symbol → {decision, item}
        self._build_ui()
        # 启动后延迟刷新（让窗口先渲染）
        self.after(300, self._refresh)

    def _build_ui(self):
        # ── 工具栏 ──────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        self._btn_refresh = ttk.Button(toolbar, text="一键刷新", command=self._refresh, width=12)
        self._btn_refresh.pack(side="left")

        self._lbl_status = ttk.Label(toolbar, text="", foreground="gray")
        self._lbl_status.pack(side="left", padx=12)

        # ── 主区域：左表格 + 右详情 ──────────────────────────────────────
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        # 左：表格
        left = ttk.Frame(paned)
        paned.add(left, weight=3)

        cols = ("symbol", "type", "action_label", "status")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                  selectmode="browse", height=18)
        self._tree.heading("symbol",       text="标的代码")
        self._tree.heading("type",         text="品种类型")
        self._tree.heading("action_label", text="投资动作")
        self._tree.heading("status",       text="状态")
        self._tree.column("symbol",       width=100, anchor="center")
        self._tree.column("type",         width=110, anchor="center")
        self._tree.column("action_label", width=150, anchor="center")
        self._tree.column("status",       width=60,  anchor="center")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # 为每个动作配置行颜色标签
        for action, bg in ACTION_BG.items():
            self._tree.tag_configure(action, background=bg, foreground=ACTION_FG.get(action, "black"))

        # 右：详情面板
        right = ttk.LabelFrame(paned, text="决策详情", padding=8)
        paned.add(right, weight=2)

        self._detail = scrolledtext.ScrolledText(
            right, wrap="word", state="disabled",
            font=("微软雅黑", 10), relief="flat", bg="#F8F8F8"
        )
        self._detail.pack(fill="both", expand=True)

    def _refresh(self):
        self._btn_refresh.config(state="disabled")
        self._lbl_status.config(text="刷新中...", foreground="#0055CC")
        self.worker.run(self._do_refresh, (), self._on_refresh_done, self._on_refresh_error)

    def _do_refresh(self):
        """在后台线程中逐标的计算决策（不调用 run_watchlist 以便直接获取 Decision）。"""
        from stock_ai_research.rules import evaluate_rules, default_rules
        from stock_ai_research.models import MarketSnapshot
        from stock_ai_research.router import detect_instrument_type

        watchlist = load_watchlist()
        rules = default_rules()
        results = []
        for item in watchlist:
            symbol = item["symbol"]
            is_qdii = item.get("is_qdii", False)
            is_fund = item.get("is_fund", False)
            fields = item.get("fields", {})
            itype = detect_instrument_type(symbol, is_qdii=is_qdii, is_fund=is_fund)
            snapshot = MarketSnapshot(symbol=symbol, instrument_type=itype, fields=fields)
            decision = evaluate_rules(snapshot, rules)
            results.append({
                "symbol": symbol,
                "instrument_type": itype.value,
                "action": decision.action,
                "status": decision.status,
                "reasons": decision.reasons,
                "triggered_rule_ids": decision.triggered_rule_ids or [],
            })
        return results

    def _on_refresh_done(self, results: list[dict]):
        self._results = {r["symbol"]: r for r in results}
        # 清空并重建表格
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for r in results:
            label = ACTION_LABEL.get(r["action"], r["action"])
            self._tree.insert("", "end", iid=r["symbol"],
                              values=(r["symbol"], r["instrument_type"], label, r["status"]),
                              tags=(r["action"],))
        now = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.config(text=f"上次刷新：{now}", foreground="gray")
        self._btn_refresh.config(state="normal")

    def _on_refresh_error(self, err: str):
        self._lbl_status.config(text=f"刷新失败：{err}", foreground="red")
        self._btn_refresh.config(state="normal")

    def _on_select(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        symbol = sel[0]
        r = self._results.get(symbol)
        if not r:
            return
        lines = [
            f"标的代码：{r['symbol']}",
            f"品种类型：{r['instrument_type']}",
            f"投资动作：{ACTION_LABEL.get(r['action'], r['action'])}",
            "",
            "触发规则：",
        ]
        for rid in r["triggered_rule_ids"]:
            lines.append(f"  • {rid}")
        lines += ["", "原因说明："]
        for reason in r["reasons"]:
            lines.append(f"  • {reason}")

        self._detail.config(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("end", "\n".join(lines))
        self._detail.config(state="disabled")

    def refresh(self):
        """供外部调用的刷新入口。"""
        self._refresh()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Tab2 — 回测分析
# ══════════════════════════════════════════════════════════════════════════════

class BacktestTab(ttk.Frame):
    def __init__(self, parent, worker: Worker):
        super().__init__(parent)
        self.worker = worker
        self._build_ui()
        self.refresh_symbols(load_watchlist())

    def _build_ui(self):
        # ── 控制栏 ──────────────────────────────────────────────────────
        ctrl = ttk.LabelFrame(self, text="回测设置", padding=10)
        ctrl.pack(fill="x", padx=8, pady=8)

        ttk.Label(ctrl, text="选择标的：").grid(row=0, column=0, sticky="w", padx=4)
        self._combo = ttk.Combobox(ctrl, state="readonly", width=18)
        self._combo.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(ctrl, text="初始资金（元）：").grid(row=0, column=2, sticky="w", padx=8)
        self._cash_var = tk.StringVar(value="100000")
        ttk.Entry(ctrl, textvariable=self._cash_var, width=12).grid(row=0, column=3, sticky="w", padx=4)

        self._gate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="启用绩效门限验证", variable=self._gate_var).grid(
            row=0, column=4, padx=12)

        self._btn_run = ttk.Button(ctrl, text="运行回测", command=self._run, width=12)
        self._btn_run.grid(row=0, column=5, padx=8)

        self._lbl_status = ttk.Label(ctrl, text="", foreground="gray")
        self._lbl_status.grid(row=1, column=0, columnspan=6, sticky="w", padx=4, pady=(4, 0))

        # ── 结果网格 ─────────────────────────────────────────────────────
        result_frame = ttk.LabelFrame(self, text="回测结果", padding=12)
        result_frame.pack(fill="both", expand=True, padx=8, pady=4)

        metrics = [
            ("交易次数",     "trades"),
            ("总收益率",     "total_return_pct"),
            ("最大回撤",     "max_drawdown_pct"),
            ("胜率",         "win_rate_pct"),
            ("Calmar 比率",  "calmar"),
            ("年化收益率",   "cagr_pct"),
            ("基准收益率",   "benchmark_return_pct"),
            ("超额收益 α",   "alpha_pct"),
            ("交易总成本",   "total_cost_pct"),
            ("盈亏比",       "profit_loss_ratio"),
            ("最大连续亏损", "max_consecutive_losses"),
        ]
        self._metric_labels: dict[str, tk.StringVar] = {}
        for i, (label, key) in enumerate(metrics):
            row, col = divmod(i, 2)
            ttk.Label(result_frame, text=f"{label}：", anchor="e", width=14).grid(
                row=row, column=col * 2, sticky="e", padx=6, pady=3)
            var = tk.StringVar(value="—")
            self._metric_labels[key] = var
            ttk.Label(result_frame, textvariable=var, anchor="w", width=14,
                      font=("微软雅黑", 10, "bold")).grid(
                row=row, column=col * 2 + 1, sticky="w", padx=6, pady=3)

        # 门限结果行
        row_gate = (len(metrics) + 1) // 2 + 1
        ttk.Separator(result_frame, orient="horizontal").grid(
            row=row_gate, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(result_frame, text="门限验证：", anchor="e", width=14).grid(
            row=row_gate + 1, column=0, sticky="e", padx=6)
        self._gate_result_var = tk.StringVar(value="—")
        self._gate_lbl = ttk.Label(result_frame, textvariable=self._gate_result_var,
                                   anchor="w", font=("微软雅黑", 10, "bold"), width=40)
        self._gate_lbl.grid(row=row_gate + 1, column=1, columnspan=3, sticky="w", padx=6)

    def refresh_symbols(self, watchlist: list[dict]):
        symbols = [item["symbol"] for item in watchlist
                   if item.get("history_csv")]
        self._combo["values"] = symbols
        if symbols and not self._combo.get():
            self._combo.set(symbols[0])

    def _run(self):
        symbol = self._combo.get()
        if not symbol:
            messagebox.showwarning("提示", "请先选择标的")
            return
        try:
            cash = float(self._cash_var.get())
        except ValueError:
            messagebox.showwarning("提示", "初始资金格式错误")
            return

        watchlist = load_watchlist()
        item = next((w for w in watchlist if w["symbol"] == symbol), None)
        if not item or not item.get("history_csv"):
            messagebox.showerror("错误", f"{symbol} 未配置历史数据 CSV 路径")
            return

        self._btn_run.config(state="disabled")
        self._lbl_status.config(text="回测运行中...", foreground="#0055CC")
        for var in self._metric_labels.values():
            var.set("计算中...")
        self._gate_result_var.set("—")

        self.worker.run(
            self._do_backtest,
            (symbol, item, cash, self._gate_var.get()),
            self._on_done,
            self._on_error,
        )

    def _do_backtest(self, symbol: str, item: dict, cash: float, check_gate: bool):
        from stock_ai_research.backtest import run_simple_backtest
        from stock_ai_research.router import detect_instrument_type
        itype = detect_instrument_type(
            symbol, is_qdii=item.get("is_qdii", False), is_fund=item.get("is_fund", False)
        )
        report = run_simple_backtest(
            symbol=symbol,
            instrument_type=itype,
            csv_path=item["history_csv"],
            initial_cash=cash,
        )
        gate_result = None
        if check_gate:
            from stock_ai_research.validation import evaluate_performance_gate, load_gate_config
            gate = load_gate_config(GATE_PATH)
            gate_result = evaluate_performance_gate(report, gate)
        return report, gate_result

    def _on_done(self, payload):
        report, gate_result = payload
        pct_keys = {"total_return_pct", "max_drawdown_pct", "win_rate_pct",
                    "cagr_pct", "benchmark_return_pct", "alpha_pct", "total_cost_pct"}
        for key, var in self._metric_labels.items():
            val = getattr(report, key, None)
            if val is None:
                var.set("—")
            elif key in pct_keys:
                var.set(fmt_pct(val))
            else:
                var.set(fmt_num(val))

        if gate_result is not None:
            if gate_result.passed:
                self._gate_result_var.set("✅ 通过绩效门限")
                self._gate_lbl.config(foreground="#1B5E20")
            else:
                fails = "、".join(gate_result.failures)
                self._gate_result_var.set(f"❌ 未通过：{fails}")
                self._gate_lbl.config(foreground="#B71C1C")
        else:
            self._gate_result_var.set("（未启用验证）")
            self._gate_lbl.config(foreground="gray")

        self._lbl_status.config(text="回测完成", foreground="gray")
        self._btn_run.config(state="normal")

    def _on_error(self, err: str):
        self._lbl_status.config(text=f"回测失败：{err}", foreground="red")
        for var in self._metric_labels.values():
            var.set("—")
        self._btn_run.config(state="normal")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Tab3 — 模拟交易
# ══════════════════════════════════════════════════════════════════════════════

class TradeTab(ttk.Frame):
    def __init__(self, parent, worker: Worker):
        super().__init__(parent)
        self.worker = worker
        self._build_ui()
        self._refresh_history()

    def _build_ui(self):
        # ── 下单表单 ─────────────────────────────────────────────────────
        form = ttk.LabelFrame(self, text="提交模拟订单", padding=12)
        form.pack(fill="x", padx=8, pady=8)

        labels = ["标的代码", "交易方向", "数量（股）", "价格（元）"]
        for i, lbl in enumerate(labels):
            ttk.Label(form, text=f"{lbl}：").grid(row=0, column=i * 2, sticky="e", padx=4)

        self._sym_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._sym_var, width=12).grid(row=0, column=1, padx=4)

        self._side_var = tk.StringVar(value="BUY")
        ttk.Combobox(form, textvariable=self._side_var,
                     values=["BUY", "SELL"], state="readonly", width=8).grid(row=0, column=3, padx=4)

        self._qty_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._qty_var, width=10).grid(row=0, column=5, padx=4)

        self._price_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._price_var, width=10).grid(row=0, column=7, padx=4)

        self._btn_submit = ttk.Button(form, text="提交模拟订单", command=self._submit, width=14)
        self._btn_submit.grid(row=0, column=8, padx=12)

        self._submit_status = ttk.Label(form, text="", foreground="gray")
        self._submit_status.grid(row=1, column=0, columnspan=9, sticky="w", padx=4, pady=(4, 0))

        # ── 订单历史 ─────────────────────────────────────────────────────
        hist_frame = ttk.LabelFrame(self, text="订单历史", padding=8)
        hist_frame.pack(fill="both", expand=True, padx=8, pady=4)

        btn_bar = ttk.Frame(hist_frame)
        btn_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_bar, text="刷新历史", command=self._refresh_history, width=10).pack(side="left")

        cols = ("time", "order_id", "symbol", "side", "qty", "price", "status")
        self._hist_tree = ttk.Treeview(hist_frame, columns=cols, show="headings", height=14)
        self._hist_tree.heading("time",     text="时间")
        self._hist_tree.heading("order_id", text="订单ID")
        self._hist_tree.heading("symbol",   text="标的")
        self._hist_tree.heading("side",     text="方向")
        self._hist_tree.heading("qty",      text="数量")
        self._hist_tree.heading("price",    text="价格")
        self._hist_tree.heading("status",   text="状态")
        self._hist_tree.column("time",     width=140)
        self._hist_tree.column("order_id", width=120)
        self._hist_tree.column("symbol",   width=80,  anchor="center")
        self._hist_tree.column("side",     width=55,  anchor="center")
        self._hist_tree.column("qty",      width=70,  anchor="e")
        self._hist_tree.column("price",    width=70,  anchor="e")
        self._hist_tree.column("status",   width=90,  anchor="center")

        vsb = ttk.Scrollbar(hist_frame, orient="vertical", command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=vsb.set)
        self._hist_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._hist_tree.tag_configure("FILLED",         background="#C8E6C9")
        self._hist_tree.tag_configure("PARTIAL_FILLED", background="#FFF9C4")
        self._hist_tree.tag_configure("CANCELED",       background="#FFCCCC")
        self._hist_tree.tag_configure("REJECTED",       background="#FFCCCC")

    def _submit(self):
        symbol = self._sym_var.get().strip()
        side = self._side_var.get()
        qty_str = self._qty_var.get().strip()
        price_str = self._price_var.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "请输入标的代码")
            return
        try:
            qty = float(qty_str)
            price = float(price_str)
            if qty <= 0 or price <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "数量和价格必须为正数")
            return

        self._btn_submit.config(state="disabled")
        self._submit_status.config(text="提交中...", foreground="#0055CC")
        self.worker.run(
            self._do_submit,
            (symbol, side, qty, price),
            self._on_submit_done,
            self._on_submit_error,
        )

    def _do_submit(self, symbol: str, side: str, qty: float, price: float):
        from stock_ai_research.trade_service import TradeService
        from stock_ai_research.models import Environment, TradeOrder
        svc = TradeService()
        order = TradeOrder(symbol=symbol, side=side, quantity=qty, price=price)
        key = uuid.uuid4().hex
        order_id, fill = svc.submit_order(
            env=Environment.PAPER,
            order=order,
            idempotency_key=key,
        )
        return {"order_id": order_id, "fill": fill}

    def _on_submit_done(self, result: dict):
        oid = result["order_id"]
        fill = result["fill"]
        self._submit_status.config(
            text=f"✅ 订单已提交：{oid[:8]}... 成交 {fill.quantity} 股 @ {fill.price}",
            foreground="#1B5E20",
        )
        self._btn_submit.config(state="normal")
        self._refresh_history()

    def _on_submit_error(self, err: str):
        self._submit_status.config(text=f"❌ 提交失败：{err}", foreground="red")
        self._btn_submit.config(state="normal")

    def _refresh_history(self):
        for iid in self._hist_tree.get_children():
            self._hist_tree.delete(iid)
        events = load_trade_events()
        for ev in reversed(events):
            ts = ev.get("ts", "")[:19].replace("T", " ")
            oid = ev.get("order_id", "")[:10] + "..."
            status = ev.get("status", "")
            payload = ev.get("payload", {})
            sym = payload.get("symbol", "")
            side = payload.get("side", "")
            qty_val = payload.get("quantity", "")
            qty_disp = f"{float(qty_val):.0f}" if qty_val != "" else ""
            price_val = payload.get("price", "")
            price_disp = f"{float(price_val):.2f}" if price_val != "" else ""
            self._hist_tree.insert("", "end",
                                   values=(ts, oid, sym, side, qty_disp, price_disp, status),
                                   tags=(status,))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Tab5 — 新闻分析
# ══════════════════════════════════════════════════════════════════════════════

class NewsTab(ttk.Frame):
    """LLM-powered news analysis tab (display only, does not affect trading signals)."""

    _PROVIDER_MAP = {
        "OpenAI":    "openai",
        "Claude":    "claude",
        "Gemini":    "gemini",
        "DeepSeek":  "deepseek",
    }
    _MODEL_DISPLAY = {
        "openai":   "gpt-4o-mini",
        "claude":   "claude-haiku-4-5-20251001",
        "gemini":   "gemini-2.0-flash",
        "deepseek": "deepseek-chat",
    }

    def __init__(self, parent, worker: Worker):
        super().__init__(parent)
        self.worker = worker
        self._build_ui()
        self.refresh_symbols(load_watchlist())

    def refresh_symbols(self, watchlist: list[dict]) -> None:
        symbols = ["大盘（市场整体）"] + [item["symbol"] for item in watchlist]
        self._sym_combo["values"] = symbols
        if not self._sym_combo.get():
            self._sym_combo.set(symbols[0] if symbols else "")

    def _build_ui(self):
        # ── 控件栏 ─────────────────────────────────────────────────────────
        ctrl = ttk.LabelFrame(self, text="分析设置", padding=10)
        ctrl.pack(fill="x", padx=8, pady=8)

        ttk.Label(ctrl, text="标的：").grid(row=0, column=0, sticky="e", padx=4)
        self._sym_combo = ttk.Combobox(ctrl, state="readonly", width=18)
        self._sym_combo.grid(row=0, column=1, padx=4)

        ttk.Label(ctrl, text="LLM 提供方：").grid(row=0, column=2, sticky="e", padx=(16, 4))
        self._provider_var = tk.StringVar(value="OpenAI")
        provider_combo = ttk.Combobox(
            ctrl, textvariable=self._provider_var,
            values=list(self._PROVIDER_MAP), state="readonly", width=12,
        )
        provider_combo.grid(row=0, column=3, padx=4)
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        self._model_var = tk.StringVar(value="gpt-4o-mini")
        ttk.Label(ctrl, textvariable=self._model_var, foreground="gray").grid(
            row=0, column=4, padx=8)

        self._btn_analyze = ttk.Button(ctrl, text="开始分析", command=self._run_analysis, width=12)
        self._btn_analyze.grid(row=0, column=5, padx=12)

        self._status_var = tk.StringVar(value="请在「配置管理」Tab 中设置 API Key，然后点击「开始分析」")
        ttk.Label(ctrl, textvariable=self._status_var, foreground="gray").grid(
            row=1, column=0, columnspan=6, sticky="w", padx=4, pady=(4, 0))

        # ── 结果区 ─────────────────────────────────────────────────────────
        results = ttk.LabelFrame(self, text="分析结果", padding=8)
        results.pack(fill="both", expand=True, padx=8, pady=4)

        # 左侧：情感徽章 + 风险徽章 + 摘要
        left = ttk.Frame(results, width=200)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        ttk.Label(left, text="市场情感", font=("微软雅黑", 9, "bold")).pack(pady=(6, 2))
        self._sentiment_badge = tk.Label(
            left, text="—", width=14, height=2,
            font=("微软雅黑", 11, "bold"), relief="groove", anchor="center",
        )
        self._sentiment_badge.pack(pady=4)

        ttk.Label(left, text="风险等级", font=("微软雅黑", 9, "bold")).pack(pady=(8, 2))
        self._risk_badge = tk.Label(
            left, text="—", width=14,
            font=("微软雅黑", 10), relief="groove", anchor="center",
        )
        self._risk_badge.pack(pady=4)

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=10)
        ttk.Label(left, text="一句话摘要：", font=("微软雅黑", 9, "bold")).pack(anchor="w")
        self._summary_label = tk.Label(
            left, text="", wraplength=185, justify="left",
            font=("微软雅黑", 9),
        )
        self._summary_label.pack(anchor="w", pady=4)

        # 右侧：核心要点 + 来源文章
        right = ttk.Frame(results)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="核心要点：", font=("微软雅黑", 9, "bold")).pack(anchor="w")
        self._kp_labels: list[tk.Label] = []
        for _ in range(3):
            lbl = tk.Label(right, text="", wraplength=450, justify="left", font=("微软雅黑", 9))
            lbl.pack(anchor="w", padx=10, pady=2)
            self._kp_labels.append(lbl)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(right, text="相关资讯（双击打开链接）：", font=("微软雅黑", 9, "bold")).pack(anchor="w")

        art_cols = ("title", "source", "time")
        self._art_tree = ttk.Treeview(right, columns=art_cols, show="headings", height=6)
        self._art_tree.heading("title",  text="标题")
        self._art_tree.heading("source", text="来源")
        self._art_tree.heading("time",   text="时间")
        self._art_tree.column("title",  width=350)
        self._art_tree.column("source", width=100, anchor="center")
        self._art_tree.column("time",   width=120, anchor="center")

        art_vsb = ttk.Scrollbar(right, orient="vertical", command=self._art_tree.yview)
        self._art_tree.configure(yscrollcommand=art_vsb.set)
        self._art_tree.pack(side="left", fill="both", expand=True)
        art_vsb.pack(side="right", fill="y")
        self._art_tree.bind("<Double-1>", self._open_article)
        self._article_urls: list[str] = []

    def _on_provider_change(self, _event=None):
        provider_key = self._PROVIDER_MAP.get(self._provider_var.get(), "openai")
        self._model_var.set(self._MODEL_DISPLAY.get(provider_key, ""))

    def _run_analysis(self):
        symbol = self._sym_combo.get()
        if not symbol:
            messagebox.showwarning("提示", "请先选择标的")
            return
        provider_key = self._PROVIDER_MAP[self._provider_var.get()]
        self._btn_analyze.config(state="disabled")
        self._status_var.set("分析中，请稍候...")
        self.worker.run(
            self._do_analysis,
            (symbol, provider_key),
            self._on_done,
            self._on_error,
        )

    def _do_analysis(self, symbol: str, provider: str):
        from stock_ai_research.llm_client import client_from_settings, load_llm_settings
        from stock_ai_research.news_analyzer import NewsAnalyzer
        from stock_ai_research.news_fetcher import NewsFetcher
        settings = load_llm_settings()
        settings["active_provider"] = provider
        llm = client_from_settings(settings)
        analyzer = NewsAnalyzer(llm, NewsFetcher())
        if symbol == "大盘（市场整体）":
            return analyzer.analyze_market()
        return analyzer.analyze_symbol(symbol)

    def _on_done(self, result):
        from stock_ai_research.news_analyzer import NewsAnalysis
        # Sentiment badge
        sentiment_cfg = {
            "bullish": ("📈 看涨",  "#C8E6C9", "#1B5E20"),
            "bearish": ("📉 看跌",  "#FFCCCC", "#B71C1C"),
            "neutral": ("➡️ 中性",  "#E0E0E0", "#424242"),
        }
        text, bg, fg = sentiment_cfg.get(result.sentiment, ("—", "#F5F5F5", "black"))
        self._sentiment_badge.config(text=text, bg=bg, fg=fg)

        # Risk badge
        risk_cfg = {
            "low":    ("风险：低",  "#C8E6C9", "#1B5E20"),
            "medium": ("风险：中",  "#FFF9C4", "#827717"),
            "high":   ("风险：高",  "#FFCCCC", "#B71C1C"),
        }
        rt, rbg, rfg = risk_cfg.get(result.risk_level, ("风险：—", "#F5F5F5", "black"))
        self._risk_badge.config(text=rt, bg=rbg, fg=rfg)

        # Summary
        summary_text = result.summary or (result.error if result.error else "（无摘要）")
        self._summary_label.config(text=summary_text)

        # Key points
        for i, lbl in enumerate(self._kp_labels):
            pt = result.key_points[i] if i < len(result.key_points) else ""
            lbl.config(text=f"• {pt}" if pt else "")

        # Articles tree
        for iid in self._art_tree.get_children():
            self._art_tree.delete(iid)
        self._article_urls = []
        for a in result.articles:
            self._art_tree.insert("", "end", values=(
                a["title"][:80],
                a["source"],
                a["published_at"][:16],
            ))
            self._article_urls.append(a.get("url", ""))

        now = datetime.now().strftime("%H:%M:%S")
        status = f"上次分析：{now}  [{result.provider} / {self._MODEL_DISPLAY.get(result.provider, '')}]"
        if result.error:
            status += f"  ⚠ {result.error}"
        self._status_var.set(status)
        self._btn_analyze.config(state="normal")

    def _on_error(self, err: str):
        self._status_var.set(f"分析失败：{err}")
        self._btn_analyze.config(state="normal")

    def _open_article(self, _event):
        import webbrowser
        sel = self._art_tree.selection()
        if not sel:
            return
        idx = self._art_tree.index(sel[0])
        if idx < len(self._article_urls) and self._article_urls[idx]:
            webbrowser.open(self._article_urls[idx])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: SymbolEditDialog — 标的编辑弹窗
# ══════════════════════════════════════════════════════════════════════════════

class SymbolEditDialog(tk.Toplevel):
    FIELD_DEFS = [
        ("price",            "当前价格",     float),
        ("premium_pct",      "折溢价 %",     float),
        ("pnl_pct",          "持仓盈亏 %",   float),
        ("rsi14",            "RSI-14",       float),
        ("ma20_pct",         "MA20偏离 %",   float),
        ("week52_low_pct",   "52周低位 %",   float),
        ("day_drawdown_pct", "日跌幅 %",     float),
        ("pb_ratio",         "PB 市净率",    float),
        ("iopv",             "IOPV",         float),
    ]

    def __init__(self, parent, item: dict | None = None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("编辑标的" if item else "添加标的")
        self.resizable(False, False)
        self._result: dict | None = None
        self._build(item or {})
        self.wait_window()

    def _build(self, item: dict):
        pad = {"padx": 8, "pady": 4}

        base = ttk.LabelFrame(self, text="基本信息", padding=10)
        base.pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(base, text="标的代码：").grid(row=0, column=0, sticky="e", **pad)
        self._sym = tk.StringVar(value=item.get("symbol", ""))
        ttk.Entry(base, textvariable=self._sym, width=16).grid(row=0, column=1, sticky="w", **pad)

        self._qdii = tk.BooleanVar(value=item.get("is_qdii", False))
        ttk.Checkbutton(base, text="QDII ETF", variable=self._qdii).grid(row=0, column=2, **pad)

        self._fund = tk.BooleanVar(value=item.get("is_fund", False))
        ttk.Checkbutton(base, text="公募基金", variable=self._fund).grid(row=0, column=3, **pad)

        ttk.Label(base, text="历史数据 CSV：").grid(row=1, column=0, sticky="e", **pad)
        self._csv = tk.StringVar(value=item.get("history_csv", ""))
        csv_entry = ttk.Entry(base, textvariable=self._csv, width=40)
        csv_entry.grid(row=1, column=1, columnspan=2, sticky="w", **pad)
        ttk.Button(base, text="浏览...", command=self._browse_csv, width=8).grid(
            row=1, column=3, **pad)

        fields_frame = ttk.LabelFrame(self, text="行情字段（留空表示不使用）", padding=10)
        fields_frame.pack(fill="x", padx=10, pady=4)

        self._field_vars: dict[str, tk.StringVar] = {}
        existing_fields = item.get("fields", {})
        for i, (key, label, _) in enumerate(self.FIELD_DEFS):
            row, col = divmod(i, 3)
            ttk.Label(fields_frame, text=f"{label}：", anchor="e", width=12).grid(
                row=row, column=col * 2, sticky="e", padx=4, pady=3)
            val = existing_fields.get(key, "")
            var = tk.StringVar(value="" if val == "" else str(val))
            self._field_vars[key] = var
            ttk.Entry(fields_frame, textvariable=var, width=10).grid(
                row=row, column=col * 2 + 1, sticky="w", padx=4, pady=3)

        # 保留未知字段
        self._extra_fields = {k: v for k, v in existing_fields.items()
                               if k not in {fd[0] for fd in self.FIELD_DEFS}}

        btn_bar = ttk.Frame(self)
        btn_bar.pack(pady=10)
        ttk.Button(btn_bar, text="确定", command=self._ok, width=10).pack(side="left", padx=8)
        ttk.Button(btn_bar, text="取消", command=self.destroy, width=10).pack(side="left", padx=8)

    def _browse_csv(self):
        path = filedialog.askopenfilename(
            title="选择历史数据 CSV",
            filetypes=[("CSV 文件", "*.csv"), ("全部文件", "*.*")],
        )
        if path:
            # 转为相对路径
            try:
                rel = Path(path).relative_to(ROOT)
                self._csv.set(str(rel).replace("\\", "/"))
            except ValueError:
                self._csv.set(path)

    def _ok(self):
        symbol = self._sym.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "标的代码不能为空", parent=self)
            return
        fields = dict(self._extra_fields)
        for key, _, typ in self.FIELD_DEFS:
            raw = self._field_vars[key].get().strip()
            if raw:
                try:
                    fields[key] = typ(raw)
                except ValueError:
                    messagebox.showwarning("提示", f"字段 {key} 格式错误", parent=self)
                    return
        self._result = {
            "symbol": symbol,
            "is_qdii": self._qdii.get(),
            "is_fund": self._fund.get(),
            "history_csv": self._csv.get().strip(),
            "fields": fields,
        }
        self.destroy()

    @property
    def result(self) -> dict | None:
        return self._result


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Tab4 — 配置管理
# ══════════════════════════════════════════════════════════════════════════════

class SettingsTab(ttk.Frame):
    def __init__(self, parent, worker: Worker, on_watchlist_saved):
        super().__init__(parent)
        self.worker = worker
        self._on_watchlist_saved = on_watchlist_saved
        self._watchlist: list[dict] = load_watchlist()
        self._settings = load_app_settings()
        self._build_ui()
        self._populate_watchlist_tree()

    def _build_ui(self):
        # 使用滚动容器
        canvas = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(event):
            canvas.itemconfig(win_id, width=event.width)
        canvas.bind("<Configure>", _on_resize)

        def _on_frame_change(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_frame_change)

        # ── A. 监控列表 ──────────────────────────────────────────────────
        wl_frame = ttk.LabelFrame(inner, text="监控列表", padding=8)
        wl_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        btn_bar = ttk.Frame(wl_frame)
        btn_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_bar, text="添加标的", command=self._add_symbol, width=10).pack(side="left", padx=4)
        ttk.Button(btn_bar, text="编辑选中", command=self._edit_symbol, width=10).pack(side="left", padx=4)
        ttk.Button(btn_bar, text="删除选中", command=self._del_symbol, width=10).pack(side="left", padx=4)
        ttk.Button(btn_bar, text="保 存", command=self._save_watchlist, width=10).pack(side="right", padx=4)

        cols = ("symbol", "qdii", "fund", "price", "csv")
        self._wl_tree = ttk.Treeview(wl_frame, columns=cols, show="headings", height=7)
        self._wl_tree.heading("symbol", text="代码")
        self._wl_tree.heading("qdii",   text="QDII")
        self._wl_tree.heading("fund",   text="基金")
        self._wl_tree.heading("price",  text="价格")
        self._wl_tree.heading("csv",    text="历史数据 CSV")
        self._wl_tree.column("symbol", width=80,  anchor="center")
        self._wl_tree.column("qdii",   width=55,  anchor="center")
        self._wl_tree.column("fund",   width=55,  anchor="center")
        self._wl_tree.column("price",  width=80,  anchor="e")
        self._wl_tree.column("csv",    width=280)
        self._wl_tree.pack(fill="both", expand=True)

        # ── B. 绩效门限 ──────────────────────────────────────────────────
        gate_frame = ttk.LabelFrame(inner, text="绩效门限配置", padding=10)
        gate_frame.pack(fill="x", padx=10, pady=4)

        gate_cfg = load_gate_cfg()
        self._gate_vars: dict[str, tk.StringVar] = {}
        gate_fields = [
            ("min_total_return_pct", "最低总收益率 %"),
            ("max_drawdown_pct",     "最大允许回撤 %"),
            ("min_calmar",           "最低 Calmar 比率"),
            ("min_win_rate_pct",     "最低胜率 %"),
        ]
        for i, (key, lbl) in enumerate(gate_fields):
            col = i % 2
            row = i // 2
            ttk.Label(gate_frame, text=f"{lbl}：", anchor="e", width=20).grid(
                row=row, column=col * 2, sticky="e", padx=6, pady=4)
            var = tk.StringVar(value=str(gate_cfg.get(key, "")))
            self._gate_vars[key] = var
            ttk.Entry(gate_frame, textvariable=var, width=10).grid(
                row=row, column=col * 2 + 1, sticky="w", padx=4, pady=4)

        ttk.Button(gate_frame, text="保存门限", command=self._save_gate, width=10).grid(
            row=2, column=0, columnspan=4, pady=8)

        # ── C. 飞书 Webhook ──────────────────────────────────────────────
        wb_frame = ttk.LabelFrame(inner, text="飞书推送（可选）", padding=10)
        wb_frame.pack(fill="x", padx=10, pady=4)

        ttk.Label(wb_frame, text="Webhook URL：").grid(row=0, column=0, sticky="e", padx=4)
        self._webhook_var = tk.StringVar(value=self._settings.get("webhook_url", ""))
        ttk.Entry(wb_frame, textvariable=self._webhook_var, width=55).grid(
            row=0, column=1, sticky="ew", padx=4)

        btn_row = ttk.Frame(wb_frame)
        btn_row.grid(row=1, column=0, columnspan=2, pady=6)
        ttk.Button(btn_row, text="保 存", command=self._save_webhook, width=10).pack(side="left", padx=6)
        ttk.Button(btn_row, text="测试发送", command=self._test_webhook, width=10).pack(side="left", padx=6)
        self._wb_status = ttk.Label(btn_row, text="", foreground="gray")
        self._wb_status.pack(side="left", padx=8)

        # ── D. LLM 配置 ──────────────────────────────────────────────────
        llm_frame = ttk.LabelFrame(inner, text="LLM 新闻分析配置", padding=10)
        llm_frame.pack(fill="x", padx=10, pady=4)

        ttk.Label(llm_frame, text="默认提供方：", anchor="e", width=18).grid(
            row=0, column=0, sticky="e", padx=4, pady=4)
        self._llm_provider_var = tk.StringVar()
        ttk.Combobox(
            llm_frame, textvariable=self._llm_provider_var,
            values=["openai", "claude", "gemini", "deepseek"],
            state="readonly", width=14,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        key_fields = [
            ("openai_key",   "OpenAI API Key"),
            ("claude_key",   "Claude API Key"),
            ("gemini_key",   "Gemini API Key"),
            ("deepseek_key", "DeepSeek API Key"),
        ]
        self._llm_key_vars: dict[str, tk.StringVar] = {}
        for i, (key, label) in enumerate(key_fields, start=1):
            ttk.Label(llm_frame, text=f"{label}：", anchor="e", width=18).grid(
                row=i, column=0, sticky="e", padx=4, pady=3)
            var = tk.StringVar()
            self._llm_key_vars[key] = var
            ttk.Entry(llm_frame, textvariable=var, width=52, show="*").grid(
                row=i, column=1, sticky="w", padx=4, pady=3)

        btn_llm_row = ttk.Frame(llm_frame)
        btn_llm_row.grid(row=len(key_fields) + 1, column=0, columnspan=2, pady=8)
        ttk.Button(btn_llm_row, text="保存 LLM 配置", command=self._save_llm_settings,
                   width=14).pack(side="left", padx=6)
        self._llm_save_status = ttk.Label(btn_llm_row, text="", foreground="gray")
        self._llm_save_status.pack(side="left", padx=6)

        self._load_llm_settings_to_ui()

        # ── E. 实盘闸门 ──────────────────────────────────────────────────
        gate_live = ttk.LabelFrame(inner, text="实盘闸门控制", padding=10)
        gate_live.pack(fill="x", padx=10, pady=(4, 10))

        ttk.Label(gate_live, text="当前状态：").grid(row=0, column=0, sticky="e", padx=6)
        self._gate_status_var = tk.StringVar(value="查询中...")
        ttk.Label(gate_live, textvariable=self._gate_status_var,
                  font=("微软雅黑", 10, "bold")).grid(row=0, column=1, sticky="w", padx=4)

        ttk.Button(gate_live, text="暂停实盘", command=self._pause_gate, width=10).grid(
            row=0, column=2, padx=12)
        ttk.Button(gate_live, text="恢复实盘", command=self._resume_gate, width=10).grid(
            row=0, column=3, padx=4)
        ttk.Button(gate_live, text="刷新状态", command=self._refresh_gate_status, width=10).grid(
            row=0, column=4, padx=4)

        self._refresh_gate_status()

    # ── 监控列表操作 ──────────────────────────────────────────────────────────

    def _populate_watchlist_tree(self):
        for iid in self._wl_tree.get_children():
            self._wl_tree.delete(iid)
        for item in self._watchlist:
            price = item.get("fields", {}).get("price", "")
            price_str = f"{float(price):.2f}" if price != "" else ""
            self._wl_tree.insert("", "end", values=(
                item["symbol"],
                "是" if item.get("is_qdii") else "",
                "是" if item.get("is_fund") else "",
                price_str,
                item.get("history_csv", ""),
            ))

    def _add_symbol(self):
        dlg = SymbolEditDialog(self)
        if dlg.result:
            self._watchlist.append(dlg.result)
            self._populate_watchlist_tree()

    def _edit_symbol(self):
        sel = self._wl_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要编辑的标的")
            return
        symbol = self._wl_tree.item(sel[0], "values")[0]
        idx = next((i for i, w in enumerate(self._watchlist) if w["symbol"] == symbol), None)
        if idx is None:
            return
        dlg = SymbolEditDialog(self, self._watchlist[idx])
        if dlg.result:
            self._watchlist[idx] = dlg.result
            self._populate_watchlist_tree()

    def _del_symbol(self):
        sel = self._wl_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的标的")
            return
        symbol = self._wl_tree.item(sel[0], "values")[0]
        if messagebox.askyesno("确认", f"确定删除 {symbol}？"):
            self._watchlist = [w for w in self._watchlist if w["symbol"] != symbol]
            self._populate_watchlist_tree()

    def _save_watchlist(self):
        save_watchlist(self._watchlist)
        messagebox.showinfo("完成", "监控列表已保存")
        self._on_watchlist_saved(self._watchlist)

    # ── 绩效门限 ──────────────────────────────────────────────────────────────

    def _save_gate(self):
        try:
            data = {k: float(v.get()) for k, v in self._gate_vars.items()}
        except ValueError:
            messagebox.showwarning("提示", "门限值必须为数字")
            return
        save_gate_cfg(data)
        messagebox.showinfo("完成", "绩效门限已保存")

    # ── 飞书 Webhook ──────────────────────────────────────────────────────────

    def _save_webhook(self):
        self._settings["webhook_url"] = self._webhook_var.get().strip()
        save_app_settings(self._settings)
        self._wb_status.config(text="已保存", foreground="green")

    def _test_webhook(self):
        url = self._webhook_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先填写 Webhook URL")
            return
        self._wb_status.config(text="发送中...", foreground="#0055CC")
        self.worker.run(self._do_test_webhook, (url,),
                        lambda _: self._wb_status.config(text="✅ 发送成功", foreground="green"),
                        lambda e: self._wb_status.config(text=f"❌ 失败：{e}", foreground="red"))

    def _do_test_webhook(self, url: str):
        payload = json.dumps({"msg_type": "text", "content": {"text": "投研平台测试推送 ✅"}}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")

    # ── 实盘闸门 ──────────────────────────────────────────────────────────────

    def _refresh_gate_status(self):
        try:
            from stock_ai_research.live_gate import LiveGate
            st = LiveGate().status()
            if st.get("paused"):
                reason = st.get("reason", "")
                self._gate_status_var.set(f"⛔ 已暂停  原因：{reason}")
            else:
                self._gate_status_var.set("✅ 运行中（实盘已开放）")
        except Exception as e:
            self._gate_status_var.set(f"查询失败：{e}")

    def _pause_gate(self):
        reason = simpledialog.askstring("暂停实盘", "请输入暂停原因（如：系统维护）：",
                                        parent=self)
        if reason is None:
            return
        try:
            from stock_ai_research.live_gate import LiveGate
            LiveGate().pause(reason or "manual_pause")
            messagebox.showinfo("完成", "实盘已暂停")
            self._refresh_gate_status()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _resume_gate(self):
        if not messagebox.askyesno("确认", "确定恢复实盘交易？"):
            return
        try:
            from stock_ai_research.live_gate import LiveGate
            LiveGate().resume()
            messagebox.showinfo("完成", "实盘已恢复")
            self._refresh_gate_status()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ── LLM 配置 ──────────────────────────────────────────────────────────────

    def _load_llm_settings_to_ui(self):
        from stock_ai_research.llm_client import load_llm_settings
        cfg = load_llm_settings()
        self._llm_provider_var.set(cfg.get("active_provider", "openai"))
        for key, var in self._llm_key_vars.items():
            var.set(cfg.get(key, ""))

    def _save_llm_settings(self):
        from stock_ai_research.llm_client import save_llm_settings
        data = {"active_provider": self._llm_provider_var.get()}
        data.update({k: v.get().strip() for k, v in self._llm_key_vars.items()})
        save_llm_settings(data)
        self._llm_save_status.config(text="已保存", foreground="green")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: App 根窗口
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("股票 AI 研究平台  v4.0")
        self.geometry("980x680")
        self.minsize(900, 600)

        # 设置全局字体和主题
        style = ttk.Style(self)
        try:
            style.theme_use("vista")   # Windows 原生风格
        except Exception:
            pass
        style.configure("Treeview", rowheight=26, font=("微软雅黑", 9))
        style.configure("Treeview.Heading", font=("微软雅黑", 9, "bold"))
        style.configure("TLabel", font=("微软雅黑", 9))
        style.configure("TButton", font=("微软雅黑", 9))
        style.configure("TLabelframe.Label", font=("微软雅黑", 9, "bold"))

        worker = Worker(self)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self._dashboard = DashboardTab(notebook, worker)
        self._backtest  = BacktestTab(notebook, worker)
        self._trade     = TradeTab(notebook, worker)
        self._news      = NewsTab(notebook, worker)
        self._settings  = SettingsTab(notebook, worker,
                                      on_watchlist_saved=self._on_watchlist_saved)

        notebook.add(self._dashboard, text="  📊 监控面板  ")
        notebook.add(self._backtest,  text="  📈 回测分析  ")
        notebook.add(self._trade,     text="  💹 模拟交易  ")
        notebook.add(self._news,      text="  📰 新闻分析  ")
        notebook.add(self._settings,  text="  ⚙️  配置管理  ")

    def _on_watchlist_saved(self, watchlist: list[dict]):
        """watchlist 保存后同步刷新各 Tab。"""
        self._backtest.refresh_symbols(watchlist)
        self._news.refresh_symbols(watchlist)
        self._dashboard.refresh()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10: 入口
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
