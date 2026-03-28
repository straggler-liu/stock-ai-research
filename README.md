# stock-ai-research

全品种投研决策平台（MVP+）代码仓库。

## 当前进度

已在当前仓库继续开发，新增了：
- 品种识别路由（A股/港股/美股/ETF/QDII/Fund/REITs）
- 分级规则引擎（L1~L3，冲突时高优先级覆盖）
- 决策编排 + 飞书卡片生成
- 历史数据回测（收益、回撤、CAGR、Calmar、Alpha）
- 绩效门槛验收（回测结果对照 gate 配置）
- 模拟盘/实盘切换执行层（`paper` / `live`）
- 交易前风控检查（仓位上限、溢价阈值、数据完整性）
- 批量 watchlist 监控与飞书 webhook 推送（含重试）
- 批量模式支持 gate 拦截（未达绩效门槛禁止 live）
- 批量回测汇总报表导出（JSON + CSV）
- 交易状态事件日志与幂等下单（防止重复提交）
- 订单状态查询与撤单接口（CLI）
- 部分成交补齐接口（CLI）
- 执行质量统计报表（成交/撤单/拒单，支持按标的/环境/日/周分组）
- 执行质量阈值告警（支持全局/标的/环境 + 7d/30d 时间窗阈值）
- 告警分级动作：yellow=记录，orange=推送，red=推送+暂停live
- batch自动读取live闸门状态并阻断live_allowed
- 标准阻断错误码：LIVE_GATE_PAUSED / PERFORMANCE_GATE_FAILED / MISSING_HISTORY_CSV / RISK_CHECK_FAILED
- exec-alert输出包含阻断码与建议动作（recommended_action）

## 目录

- `docs/`：开发手册文档
- `configs/`：示例监控配置与绩效门槛
- `data/`：示例历史数据
- `src/stock_ai_research/`：核心代码
- `tests/`：单元测试

## 快速开始

### 安装

```bash
python -m pip install -e .
```

### 1) 单次决策

```bash
stock-ai-research decision \
  --symbol 513310 \
  --is-qdii \
  --fields '{"price":3.792,"iopv":3.1614,"premium_pct":19.95,"pnl_pct":8.2}'
```

### 2) 历史回测

```bash
stock-ai-research backtest \
  --symbol 513310 \
  --is-qdii \
  --csv data/sample_history_qdii.csv
```

### 3) 绩效门槛验收

```bash
stock-ai-research validate \
  --symbol 513310 \
  --is-qdii \
  --csv data/sample_history_qdii.csv \
  --gate configs/performance_gate.json
```

### 4) 模拟盘下单（paper）

```bash
stock-ai-research trade \
  --env paper --symbol 513310 --side BUY --quantity 100 --price 3.2 \
  --latest-fields '{"price":3.2,"premium_pct":1.2}' \
  --idempotency-key trade-paper-001
```

### 5) 实盘模式演示（live，双确认令牌）

```bash
stock-ai-research trade \
  --env live --symbol 513310 --side BUY --quantity 100 --price 3.2 \
  --latest-fields '{"price":3.2,"premium_pct":1.2}' \
  --confirm-token LIVE_OK --risk-token RISK_OK \
  --idempotency-key trade-live-001
```

### 6) 批量监控（可选推送飞书）

```bash
stock-ai-research batch \
  --config configs/sample_watchlist.json \
  --webhook 'https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook'
```

### 7) 批量监控 + 绩效门槛拦截

```bash
stock-ai-research batch \
  --config configs/sample_watchlist.json \
  --enforce-gate \
  --gate configs/performance_gate.json
```

### 8) 导出批量回测报表

```bash
stock-ai-research report \
  --config configs/sample_watchlist.json \
  --out-json data/backtest_report.json \
  --out-csv data/backtest_report.csv
```


### 9) 查询订单状态

```bash
stock-ai-research order-status --order-id <ORDER_ID>
```

### 10) 撤单

```bash
stock-ai-research cancel --order-id <ORDER_ID>
```

> 若订单为 `PARTIAL_FILLED`，撤单会返回已成交数量与剩余撤销量。

### 11) 将部分成交订单补齐

```bash
stock-ai-research complete --order-id <ORDER_ID>
```

### 12) 导出执行质量统计报表

```bash
stock-ai-research exec-report \
  --events-log data/trade_events.jsonl \
  --out-json data/execution_quality_report.json
```


### 13) 执行质量阈值告警

```bash
stock-ai-research exec-alert \
  --events-log data/trade_events.jsonl \
  --alert-config configs/execution_alerts.json \
  --webhook 'https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook'
```


### 14) Live闸门状态与控制

```bash
# 查看状态
stock-ai-research live-gate --action status

# 手动暂停
stock-ai-research live-gate --action pause --reason manual_pause

# 手动恢复
stock-ai-research live-gate --action resume
```

## 测试

```bash
pytest -q
```
