# Local Market Agent：项目总方案与执行计划

**版本**：v0.1  
**状态**：Source of Truth / 项目基准文档  
**日期**：2026-06-04  
**Owner**：Hanzhi  
**目标**：本地运行 AI，分析公开市场，在严格风控和可验证 edge 的前提下，逐步从 research → paper trading → 小额实盘。

> 重要声明：本文档是工程与研究计划，不是投资建议、法律建议或税务建议。任何实盘之前必须重新确认平台资格、地区限制、资金路径、税务责任和 API 权限。默认模式永远是 read-only + paper trading。

---

## 0. 项目一句话定义

**Local Market Agent 是一个本地优先的公开市场研究、概率评估、回测、模拟盘和小额实盘前置风控系统。**

它不是“让 LLM 直接买卖”的 bot，而是一个可审计的交易研究机器：

```text
公开数据 → 本地缓存 → 证据抽取 → 多角色研究 → 概率估计 → 策略规则 → 风控闸门 → paper ledger → 绩效复盘
```

第一阶段的目标不是立刻赚钱，而是快速看到系统在工作，并用真实公开市场数据判断我们有没有 edge。

---

## 1. 已知个人条件与设计约束

### 1.1 当前硬件

- MacBook Air M4，24GB 内存：主力开发机、本地 dashboard、SQLite/DuckDB、本地 LLM 服务、任务编排。
- RTX 2070 Max-Q 游戏本：备用 CUDA 推理机，用于 7B/8B 量化模型、embedding 或批量摘要实验。
- 结论：**v0.1–v0.3 不买任何新硬件。**

### 1.2 当前资金

- 初始可动用资金：约 1000–2000 HKD。
- 资金主要在香港 HSBC 银行卡。
- 结论：**Phase 0–7 不使用真钱交易；最多用 0–200 HKD 测 API/域名/小工具。实盘最早放到 paper 达标之后，首批实盘池 300–500 HKD。**

### 1.3 个人优势

- 能使用 Codex 和 Python 工程流。
- 已经熟悉 agent、pipeline、evaluation、repo 结构、自动化系统。
- 更适合做“信息分析型 edge”和可审计系统，而不是低延迟交易基础设施。

---

## 2. 调研后的核心判断

### 2.1 不做什么

第一阶段明确不做：

```text
不做高频交易
不做全自动真钱下单
不做杠杆
不做期权、期货、perps
不做做空
不做绕过地区限制
不把 HSBC 主资金接入自动化系统
不让 LLM 直接决定买卖
```

原因很直接：当前资金和硬件不适合低延迟交易；LLM 的优势也不在毫秒级执行，而在信息阅读、证据整理、反方论证、概率辅助、日志审计。

### 2.2 LLM 在本项目中的角色

LLM 只做：

```text
研究员
证据整理器
反方论证器
概率估计辅助器
报告生成器
日志审计器
```

LLM 不做：

```text
最终下单者
风险豁免者
资金管理者
地区/法律合规判断的最终责任人
```

最终执行结构：

```text
LLM = 研究与证据层
Strategy = 规则层
Risk Engine = 硬闸门
Human = 实盘批准人
```

### 2.3 为什么优先 Prediction Markets

Prediction markets 天然适合 LLM：市场问题结构化，价格可以解释为隐含概率，研究对象通常是事件是否发生。我们可以比较：

```text
市场隐含概率 vs 本地研究 agent 概率估计
```

然后用 paper trading 验证是否真的存在信息分析 edge。

---

## 3. 市场与接口选择

### 3.1 Prediction Markets：第一优先级

#### Polymarket

调研结论：Polymarket 的 Gamma API、Data API 和 CLOB read endpoints 是公开读取，不需要认证；orderbook、prices、spreads 等读端点可以用于 read-only 市场分析。交易端点需要认证和签名。平台也有 geoblock 机制，blocked regions 的订单会被拒绝，并且禁止使用 VPN 等工具绕过地区限制。

项目处理方式：

```text
v0.1：只读 Polymarket market data，不接交易端点
v0.2：加入 market screening、价格历史、spread/liquidity 过滤
v1.0 以后：只有在平台资格、地区限制和资金路径确认后，才考虑小额实盘
```

#### Kalshi

调研结论：Kalshi 提供 REST、WebSocket、FIX API，并提供 demo environment。国际用户资格取决于会员协议和地区限制；国际用户可用入出金方式也受限制，wire transfer 最低额较高，不适合当前小资金快速试验。

项目处理方式：

```text
v0.1：Kalshi demo/read-only adapter
v0.2：事件市场搜索、对照 Polymarket 同类事件
v1.0 以后：只在资格和资金路径清楚时考虑真实交易
```

### 3.2 Crypto Spot：第二优先级

调研结论：crypto API 生态成熟，CCXT 可统一访问多个交易所的公开/私有 API，适合行情、orderbook、OHLCV、策略研究和模拟盘。香港用户实盘平台要优先考虑 SFC 持牌平台。SFC 会公布正式持牌虚拟资产交易平台名单，同时也提醒名单发布不代表保证平台表现或信用。

项目处理方式：

```text
v0.1：只做 crypto public data / OHLCV / paper trading
v0.2：BTC/ETH trend + news veto
v1.0 以后：如要实盘，优先研究香港持牌平台；API key 不能有提现权限；只做 spot
```

平台备注：

- HashKey API 支持下单、撤单、订单查看、行情流和账户数据，REST/WebSocket 均可用。
- OSL 的 API 对 retail investors 不开放，只适合专业/机构投资者路径，暂不作为第一实盘接口。

### 3.3 股票/ETF：第三优先级

调研结论：Alpaca paper account 可用于 paper trading 和 API 练习，但 paper-only 账户只能使用 IEX market data，且 paper trading 不等同真实成交。IBKR TWS API 支持通过 TWS/IB Gateway 用 TCP Socket 接入，支持 Python；Futu/Moomoo OpenAPI 支持本地 OpenD、Python SDK、实盘与模拟交易。

项目处理方式：

```text
v0.1：yfinance + SEC EDGAR + GDELT + paper research
v0.2：Alpaca paper trading adapter
v1.5 以后：再考虑 IBKR/Futu/Moomoo 的真实接口
```

---

## 4. 本地硬件与 LLM 方案

### 4.1 MacBook Air M4 24GB

主力职责：

```text
Python 项目开发
SQLite/DuckDB 本地数据库
Streamlit dashboard
LM Studio / Ollama 本地模型服务
定时任务与本地报告生成
```

Ollama 支持 Apple 设备通过 Metal API 做 GPU 加速；LM Studio 支持本地 OpenAI-compatible endpoints，可以让项目通过统一 client 调用本地模型。

### 4.2 RTX 2070 Max-Q

备用职责：

```text
7B/8B 量化模型实验
embedding 批处理
小型分类器/摘要实验
CUDA 相关本地推理测试
```

不作为 v0.1 的硬依赖。v0.1 必须能只用 MacBook 跑通。

### 4.3 本地模型策略

```text
开发与测试：MockLLMProvider，完全离线、确定性输出
日常运行：LM Studio 或 Ollama，OpenAI-compatible provider
复杂判断：未来可加多模型交叉检查，但不在 v0.1 强制实现
```

不追求一开始跑 32B/70B。这个项目早期瓶颈是数据、证据链、评估和风控，不是模型参数量。

---

## 5. 总体系统架构

```text
公开数据源
  ├─ Polymarket / Kalshi markets
  ├─ Crypto spot OHLCV / orderbook
  ├─ yfinance / Alpha Vantage
  ├─ SEC EDGAR filings
  ├─ GDELT / RSS / NewsAPI
  └─ 手动 watchlist / notes

        ↓

Data Ingestion Layer
  ├─ adapters
  ├─ normalization
  ├─ timestamping
  └─ raw response cache

        ↓

Evidence Store
  ├─ SQLite / DuckDB
  ├─ raw snapshots
  ├─ extracted evidence
  ├─ source metadata
  └─ audit log

        ↓

Research Agent Layer
  ├─ researcher
  ├─ skeptic
  ├─ probability estimator
  ├─ uncertainty auditor
  └─ report writer

        ↓

Strategy Layer
  ├─ prediction market edge rule
  ├─ crypto trend + news veto
  ├─ equity event monitor
  └─ no-trade filters

        ↓

Risk Layer
  ├─ max position size
  ├─ max daily loss
  ├─ max drawdown
  ├─ liquidity/spread filter
  ├─ confidence threshold
  ├─ compliance/geoblock check
  └─ live trading kill switch

        ↓

Paper Trading Layer
  ├─ simulated orders
  ├─ simulated fills
  ├─ ledger
  ├─ positions
  └─ performance metrics

        ↓

Dashboard + Daily Report
  ├─ watchlist
  ├─ research brief
  ├─ signals
  ├─ veto reasons
  ├─ paper PnL
  └─ calibration metrics
```

---

## 6. 代码结构规划

```text
local-market-agent/
  pyproject.toml
  README.md
  .env.example
  docs/
    PROJECT_SPEC.md
    SAFETY_AND_RISK.md
    MARKET_SELECTION.md
    LIVE_TRADING_CHECKLIST.md
    DATA_SOURCES.md
  data/
    fixtures/
    raw_cache/
    research_briefs/
    paper_trades.jsonl
    local_market_agent.sqlite
  src/local_market_agent/
    adapters/
      polymarket.py
      kalshi.py
      crypto_ccxt.py
      yfinance_adapter.py
      sec_edgar.py
      gdelt.py
      newsapi.py
      manual.py
      fixture.py
    agents/
      researcher.py
      skeptic.py
      calibrator.py
      reporter.py
    backtest/
      engine.py
      metrics.py
    config/
      settings.py
    eval/
      calibration.py
      brier.py
      performance.py
    llm/
      base.py
      mock.py
      openai_compatible.py
      lmstudio.py
      ollama.py
    paper/
      ledger.py
      fills.py
      positions.py
    reporting/
      daily_report.py
      markdown_report.py
    risk/
      rules.py
      sizing.py
      kill_switch.py
      compliance.py
    schemas/
      market.py
      evidence.py
      brief.py
      signal.py
      risk.py
      paper.py
      performance.py
    storage/
      sqlite.py
      repositories.py
    strategy/
      prediction_market_edge.py
      crypto_trend_news_veto.py
      equity_event_monitor.py
    cli.py
  tests/
  ui/
    app.py
```

---

## 7. 核心 Schema

### 7.1 ResearchBrief

```json
{
  "brief_id": "string",
  "market_id": "string",
  "asset_type": "prediction_market | crypto | equity",
  "timestamp_utc": "datetime",
  "question": "string",
  "market_price": 0.52,
  "market_implied_probability": 0.52,
  "thesis": "string",
  "evidence": [
    {
      "source": "string",
      "timestamp_utc": "datetime",
      "claim": "string",
      "relevance": 0.0,
      "reliability": 0.0
    }
  ],
  "counter_evidence": [],
  "base_rate": 0.0,
  "estimated_probability": 0.0,
  "confidence": 0.0,
  "uncertainty_notes": "string",
  "recommended_action": "observe | paper_buy_yes | paper_buy_no | paper_sell | skip",
  "reason_for_action": "string",
  "must_not_trade_reasons": []
}
```

### 7.2 Signal

```json
{
  "signal_id": "string",
  "brief_id": "string",
  "market_id": "string",
  "strategy_name": "prediction_market_edge",
  "timestamp_utc": "datetime",
  "action": "observe | skip | paper_buy_yes | paper_buy_no | paper_sell",
  "market_probability": 0.52,
  "agent_probability": 0.64,
  "estimated_edge": 0.12,
  "spread": 0.03,
  "confidence": 0.72,
  "reason": "string"
}
```

### 7.3 RiskDecision

```json
{
  "risk_decision_id": "string",
  "signal_id": "string",
  "timestamp_utc": "datetime",
  "approved": false,
  "veto_reasons": ["low_confidence", "wide_spread"],
  "max_position_size": 0.0,
  "requires_human_approval": true,
  "live_trading_allowed": false
}
```

### 7.4 PaperOrder

```json
{
  "paper_order_id": "string",
  "signal_id": "string",
  "risk_decision_id": "string",
  "market_id": "string",
  "timestamp_utc": "datetime",
  "side": "BUY_YES | BUY_NO | SELL | OBSERVE",
  "paper_price": 0.41,
  "size": 10,
  "fee_assumption": 0.0,
  "slippage_assumption": 0.0,
  "status": "open | closed | cancelled",
  "exit_price": null,
  "pnl": null
}
```

关键要求：**PaperOrder 必须引用 Signal 和 RiskDecision。没有通过风控链路的 order 不允许写入 ledger。**

---

## 8. Data Adapter 设计

v0.1 优先实现：

```text
FixtureAdapter：离线测试用
PolymarketAdapter：public markets / prices / orderbook / prices-history
KalshiAdapter：demo/public market listing placeholder
YFinanceAdapter：OHLCV 历史数据
SecEdgarAdapter：company submissions / filings metadata
GdeltAdapter：news search / event context
```

所有 adapter 必须满足：

```text
read-only 默认
超时处理
HTTP error handling
raw response cache
normalized schema output
network tests marked optional
不存 API key
不实现 real-money trading endpoints
```

SEC EDGAR 的 data.sec.gov REST API 不需要认证或 API key，适合作为美股事件研究数据源。GDELT 提供全球新闻/事件 open data firehose，适合做新闻证据层。NewsAPI 可作为开发测试，但免费计划有 100 requests/day、24h delay 和 1 个月历史限制，所以不能当核心生产源。

---

## 9. Strategy 设计

### 9.1 PredictionMarketEdgeStrategy

输入：

```text
market_implied_probability
agent_estimated_probability
bid_ask_spread
liquidity_depth
time_to_resolution
evidence_quality
resolution_ambiguity
confidence
```

规则：

```text
如果 evidence_quality < 0.65 → skip
如果 confidence < 0.60 → skip
如果 spread > 0.08 → skip
如果 liquidity_depth 太低 → skip
如果 resolution source 模糊 → skip
如果 abs(agent_probability - market_probability) < max(0.08, 2 * spread) → observe
否则生成 paper signal
```

简化 EV：

```text
EV_yes = p_agent - best_ask_yes
EV_no = (1 - p_agent) - best_ask_no
```

只在 EV 明确为正，且超过 spread/fee/slippage 缓冲时，才允许进入 paper order。

### 9.2 CryptoTrendNewsVetoStrategy

第一版只做 BTC/ETH spot paper：

```text
只做 spot
只观察 BTC/ETH
不做杠杆
不做做空
趋势信号由规则产生
LLM 只解释新闻风险并给 veto 建议
```

### 9.3 EquityEventMonitorStrategy

第一版只做研究，不做真钱：

```text
SEC filings
earnings dates
major news
price reaction
sector context
paper buy/sell/hold
```

---

## 10. 风控系统

风控必须是硬规则，不能被 LLM 覆盖。

默认配置：

```text
REAL_MONEY_ENABLED = false
ALLOW_LIVE_ORDERS = false
HUMAN_APPROVAL_REQUIRED = true
max_position_pct = 1%
max_daily_loss_pct = 2%
max_total_drawdown_pct = 5%
max_open_positions = 5
min_confidence = 0.60
min_edge = 0.08
max_spread = 0.08
no_leverage = true
no_derivatives = true
```

实盘前必须追加：

```text
API key 不允许 withdrawal 权限
能设置 IP whitelist 就必须设置
交易平台账户只放试验资金
HSBC 主账户不直连自动化系统
每天最多 N 笔
连续 3 笔亏损自动停机
单日亏损到阈值自动停机
地区/平台限制不明确 → 禁止交易
```

风控输出必须可审计：

```text
approved: true/false
veto_reasons: list[str]
requires_human_approval: true/false
live_trading_allowed: false by default
```

---

## 11. Paper Trading 与评估

### 11.1 Paper Ledger

每次 paper trade 记录：

```text
timestamp
market_id
brief_id
signal_id
risk_decision_id
side
paper_price
size
fee/slippage assumptions
status
exit_price
PnL
```

### 11.2 Prediction Market 评估指标

```text
Brier score
calibration curve
average edge at entry
realized EV
hit rate
average spread paid
max drawdown
number of risk vetoes
resolution ambiguity errors
```

### 11.3 Crypto/Equity Paper 评估指标

```text
net return after assumed fees
Sharpe / Sortino
max drawdown
win rate
profit factor
average win vs average loss
turnover
slippage sensitivity
performance vs buy-and-hold
performance vs random baseline
```

### 11.4 实盘前最低门槛

```text
至少 30 天 paper trading
至少 50 个独立 decision logs
至少 20 个实际 paper positions
保守成本假设后净收益为正
最大回撤 < 5%
没有一次违反风控
每个 signal 都能追溯到 evidence
agent 概率校准没有明显偏差
```

如果 agent 常说 70%，但真实发生率只有 50%，不允许实盘。

---

## 12. 资金计划

当前 1000–2000 HKD 的使用：

```text
0 HKD：硬件
0–100 HKD：域名/可选
0–200 HKD：API 小额测试/可选
0 HKD：第一阶段真钱交易
剩余资金：留在 HSBC
```

paper trading 达标后的第一批实盘：

```text
总实盘池：300–500 HKD
单笔风险：10–30 HKD
单市场最大敞口：50 HKD
总亏损到 100 HKD：停止
```

核心原则：早期最重要的资产不是本金，而是数据、日志、策略评估和工程系统。

---

## 13. 里程碑路线图

### Phase 0：项目规格冻结，1 天

产出：

```text
README.md
docs/PROJECT_SPEC.md
docs/SAFETY_AND_RISK.md
docs/MARKET_SELECTION.md
.env.example
```

验收：

```text
明确 read-only 默认
明确 no live trading
明确风控优先
明确第一阶段市场：Polymarket/Kalshi read-only + crypto/equity paper
```

### Phase 1：本地骨架，2–3 天

目标：项目能跑起来，有 CLI、配置、数据库、测试。

CLI：

```text
lma ingest-demo
lma generate-brief
lma risk-check
lma paper-log
lma report-daily
```

验收：

```text
pytest 全过
不需要联网也能跑 demo
不需要 API key
mock LLM 可生成固定 brief
```

### Phase 2：只读数据接入，3–5 天

优先顺序：

```text
1. Polymarket public markets / prices / orderbook
2. Kalshi demo/public markets
3. yfinance historical OHLCV
4. SEC EDGAR submissions
5. GDELT news
```

验收：

```text
能搜索市场
能拉取价格和 orderbook
能缓存原始 response
能生成 normalized MarketSnapshot
能处理请求失败和限速
```

### Phase 3：Research Agent，3–5 天

Agent 分工：

```text
Researcher：找支持证据
Skeptic：找反证据
Calibrator：给概率和不确定性
Reporter：输出人类可读报告
```

验收：

```text
给一个 market_id 能输出 JSON brief
brief 能保存到本地
dashboard 能展示 thesis / evidence / counter-evidence / probability
```

### Phase 4：Strategy + Risk，3–4 天

验收：

```text
低 confidence 必须 veto
spread 太大必须 veto
edge 不够必须 observe
所有 veto 都要写明原因
LLM 不能绕过风控
```

### Phase 5：Paper Trading Ledger，3–4 天

验收：

```text
每个 paper order 都能追溯到 signal、brief、risk decision
能输出 open positions
能输出 realized/unrealized PnL
能导出 JSONL/CSV
```

### Phase 6：Dashboard，2–3 天

页面：

```text
Watchlist
Market Brief
Signals
Risk Decisions
Paper Ledger
Performance Report
Settings
```

验收：

```text
streamlit run ui/app.py works
dashboard reads local data
can inspect brief → signal → risk → paper order chain
```

### Phase 7：连续 paper run，2–4 周

每日流程：

```text
拉取 watchlist
生成 brief
生成 signal
风控过滤
paper log
输出 daily report
```

每周复盘：

```text
哪些判断对
哪些判断错
错因是数据缺失、模型幻觉、规则不合理、流动性问题，还是市场随机性
是否需要调阈值
是否加入/移除数据源
```

### Phase 8：小额实盘预备，不早于第 5–6 周

进入条件：

```text
paper trading 达标
平台资格确认
API key 权限最小化
账户只放 300–500 HKD
所有 live order 默认需要人工确认
```

第一笔实盘只验证管线，不追求收益：

```text
订单能否正确提交
成交记录能否正确回读
手续费/滑点是否和假设接近
风控是否能阻止超额下单
```

---

## 14. 14 天最快可见效果版本

```text
Day 1–2：repo 骨架 + schema + mock brief
Day 3–4：Polymarket read-only adapter + fixture cache
Day 5–6：research brief generator
Day 7：prediction market edge strategy + risk veto
Day 8–9：paper ledger
Day 10：Streamlit dashboard
Day 11–14：每天跑 5–10 个市场，记录 paper decisions，出第一份 performance report
```

14 天后应该看到：

```text
系统每天自动拉市场
自动生成研究 brief
自动估概率
自动判断有没有 edge
自动 veto 不合格机会
自动记录模拟交易
自动显示表现
```

---

## 15. 第一批 Watchlist 原则

优先：

```text
AI model release / product launch
company earnings-related event
macro data release
crypto ETF / regulatory event
large tech company milestone
clearly resolvable legal/regulatory event
BTC / ETH spot observation
NVDA / AMD / MSFT / GOOGL / META / AAPL / TSLA paper research
0700.HK / 9988.HK / 3690.HK paper research
```

暂时避开：

```text
体育小盘口
名人八卦
低流动性 meme 市场
resolution source 模糊的市场
spread 很宽的市场
过期太近且信息已经充分反映的市场
```

---

## 16. Codex 执行任务

原则：**不要让 Codex 一次性写完整系统。每一步都要有测试、验收和代码审查。**

### Codex Task 1：创建 repo 骨架

```text
Create a new Python 3.11+ project named local-market-agent.

This is a local-first market research and paper-trading system. It must not implement real-money trading in v0.1.

Create:
- pyproject.toml
- README.md
- docs/PROJECT_SPEC.md
- docs/SAFETY_AND_RISK.md
- src/local_market_agent/
- tests/
- ui/app.py
- data/fixtures/

Use:
- typer for CLI
- pydantic for schemas
- sqlite or duckdb for local storage
- pytest for tests
- ruff for linting

Add CLI commands:
- ingest-demo
- generate-brief
- risk-check
- paper-log
- report-daily

All commands must run offline using fixtures. Add unit tests. Do not require API keys. Do not implement live order execution.
```

验收：

```text
uv run pytest
uv run lma ingest-demo
uv run lma generate-brief --fixture data/fixtures/demo_market.json
```

### Codex Task 2：schemas + storage

```text
Implement core schemas and local storage.

Schemas:
- Market
- MarketSnapshot
- EvidenceItem
- ResearchBrief
- Signal
- RiskDecision
- PaperOrder
- Position
- PerformanceReport

Storage:
- SQLite-backed repository
- save/load market snapshots
- save/load briefs
- save/load signals
- save/load risk decisions
- append paper orders

Add tests for serialization, validation, and storage roundtrip.
```

验收：

```text
所有 schema 有 strict validation
paper order 必须引用 signal_id 和 risk_decision_id
```

### Codex Task 3：LLM provider abstraction

```text
Implement LLM provider abstraction.

Providers:
- MockLLMProvider for tests
- OpenAICompatibleProvider with configurable base_url, api_key, model

The OpenAICompatibleProvider should work with local LM Studio or Ollama-compatible endpoints when configured.

Do not call external APIs in tests.
Add structured JSON output validation and retry-on-invalid-json for runtime only.
```

验收：

```text
mock provider 生成稳定 ResearchBrief
invalid JSON 会被捕获
tests offline pass
```

### Codex Task 4：read-only market adapters

```text
Implement read-only adapters.

Adapters:
- PolymarketAdapter: fetch public markets and prices/orderbook where available
- KalshiAdapter: demo/public market listing placeholder with clear interface
- YFinanceAdapter: historical OHLCV
- SecEdgarAdapter: company submissions endpoint
- GdeltAdapter: news search endpoint
- FixtureAdapter for offline tests

All adapters must:
- be read-only
- cache raw responses
- normalize into MarketSnapshot or EvidenceItem
- handle HTTP errors, timeouts, and rate limits

No trading endpoints. No private keys. No API secrets in code.
```

验收：

```text
fixture tests pass
network tests marked optional
raw response cache exists
```

### Codex Task 5：research brief generator

```text
Build the research pipeline.

Input:
- market_id or fixture market
- market snapshot
- evidence items

Process:
- summarize evidence
- generate thesis
- generate counter-evidence
- estimate probability
- output ResearchBrief schema

Constraints:
- confidence must be lower if evidence is sparse
- no trade recommendation may be made without evidence
- output must include uncertainty_notes
- output must include must_not_trade_reasons when applicable

Add tests with mock LLM.
```

验收：

```text
brief JSON schema valid
sparse evidence lowers confidence
missing market price prevents paper_buy recommendation
```

### Codex Task 6：strategy + risk engine

```text
Implement strategy and risk modules.

Strategy:
- PredictionMarketEdgeStrategy
- CryptoTrendNewsVetoStrategy placeholder
- EquityEventMonitorStrategy placeholder

PredictionMarketEdgeStrategy:
- compare estimated_probability with market_implied_probability
- account for spread
- require min_edge
- produce observe/skip/paper_buy_yes/paper_buy_no

Risk engine:
- max_position_pct
- max_daily_loss_pct
- max_open_positions
- min_confidence
- max_spread
- no_live_trading
- compliance_requires_manual_approval

Every signal must pass through risk before paper order.

Add unit tests for all veto paths.
```

验收：

```text
low confidence → veto
wide spread → veto
insufficient edge → observe
live trading attempt → veto
```

### Codex Task 7：paper trading ledger

```text
Implement paper trading ledger.

Features:
- create paper order from approved risk decision
- simulate fill at configured price
- track open positions
- close position
- compute realized/unrealized PnL
- export JSONL/CSV

Assumptions:
- no real orders
- configurable fees and slippage
- deterministic fill model for tests

Add tests for PnL and position lifecycle.
```

验收：

```text
paper order cannot exist without approved risk decision
PnL calculation correct
daily report includes trades, open positions, drawdown
```

### Codex Task 8：Streamlit dashboard

```text
Build Streamlit dashboard under ui/app.py.

Pages:
- Watchlist
- Market Brief
- Signals
- Risk Decisions
- Paper Ledger
- Performance Report
- Settings

Use local SQLite data.
No live trading buttons.
No secrets displayed.
```

验收：

```text
streamlit run ui/app.py works
dashboard reads local data
can inspect brief → signal → risk → paper order chain
```

---

## 17. 工程原则

```text
所有判断都可追溯
默认只读
风控不可被 LLM 覆盖
本地优先，但不迷信本地模型
先验证 edge，再考虑赚钱
任何实盘都必须最小资金、最小权限、人工确认
```

代码审查重点：

```text
是否出现 live order endpoint
是否出现私钥/API key 明文
是否绕开 risk engine
是否没有测试就接入网络
是否把 LLM 输出直接当交易指令
是否没有保存 evidence/source/timestamp
```

---

## 18. 实盘前 Checklist

只有全部满足才能进入 Phase 8：

```text
[ ] Paper trading 至少 30 天
[ ] 至少 50 个独立 decision logs
[ ] 至少 20 个 paper positions
[ ] 保守成本后净收益为正
[ ] 最大回撤 < 5%
[ ] 没有风控违规
[ ] Signal 能追溯到 evidence/brief/risk decision
[ ] 概率校准可接受
[ ] 平台地区资格确认
[ ] 入金/出金路径确认
[ ] 税务责任初步确认
[ ] API key 无提现权限
[ ] IP whitelist 或等价安全措施已设置
[ ] 账户只放 300–500 HKD 试验资金
[ ] Live order 默认人工确认
[ ] Kill switch 已测试
```

---

## 19. 参考来源与调研依据

访问日期：2026-06-04。未来执行到实盘前必须重新核对。

1. Polymarket API Introduction: https://docs.polymarket.com/api-reference/introduction
2. Polymarket Authentication: https://docs.polymarket.com/api-reference/authentication
3. Polymarket Market Data Overview: https://docs.polymarket.com/market-data/overview
4. Polymarket Geographic Restrictions: https://docs.polymarket.com/api-reference/geoblock
5. Polymarket Help - Geographic Restrictions: https://help.polymarket.com/en/articles/13364163-geographic-restrictions
6. Kalshi API Documentation: https://docs.kalshi.com/welcome
7. Kalshi Demo Environment: https://docs.kalshi.com/getting_started/demo_env
8. Kalshi International Users Help: https://help.kalshi.com/en/articles/14026044-can-i-trade-on-kalshi-from-outside-the-united-states
9. Alpaca Paper Trading: https://docs.alpaca.markets/us/docs/paper-trading
10. SFC List of Virtual Asset Trading Platforms: https://www.sfc.hk/en/Welcome-to-the-Fintech-Contact-Point/Virtual-assets/Virtual-asset-trading-platforms-operators/Lists-of-virtual-asset-trading-platforms
11. HashKey API FAQ: https://support.hashkey.com/hc/en-gb/articles/22318218414361-API-Frequently-Asked-Questions
12. OSL API Availability: https://www.osl.com/hk-en/support/where-can-i-find-information-on-api-s-offered-by-osl-s-platform
13. Futu API Documentation: https://openapi.futunn.com/futu-api-doc/en/
14. Futu Paper Trading QA: https://openapi.futunn.com/futu-api-doc/en/qa/trade.html
15. IBKR TWS API: https://www.interactivebrokers.com/campus/ibkr-api-page/trader-workstation-api/
16. IBKR TWS API Setup and Paper Compatibility: https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/
17. Ollama GPU Support: https://docs.ollama.com/gpu
18. LM Studio OpenAI Compatibility: https://lmstudio.ai/docs/developer/openai-compat
19. SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
20. GDELT Project: https://www.gdeltproject.org/
21. GDELT 2.0 15-minute updates: https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/
22. NewsAPI Pricing: https://newsapi.org/pricing
23. X API Pricing: https://docs.x.com/x-api/getting-started/pricing
24. CCXT Documentation: https://docs.ccxt.com/
25. vectorbt Documentation: https://vectorbt.dev/
26. backtesting.py Documentation: https://kernc.github.io/backtesting.py/
27. Freqtrade Documentation: https://www.freqtrade.io/en/stable/
28. NautilusTrader Strategy Docs: https://nautilustrader.io/docs/latest/concepts/strategies/
29. TradingAgents paper: https://arxiv.org/abs/2412.20138
30. AI-Trader Benchmark: https://arxiv.org/abs/2512.10971
31. LiveTradeBench: https://arxiv.org/abs/2511.03628
32. StockBench: https://arxiv.org/abs/2510.02209

---

## 20. 后续执行约定

之后所有开发都按本文档作为基准：

```text
先完成 Phase 0 和 Codex Task 1
每个 task 完成后跑测试
每个新增模块都要有 fixture/offline test
每次引入真实 API 都必须先 read-only
任何 live trading 相关代码默认禁止，除非专门创建 Phase 8 分支并通过 checklist
```

本文档放入项目后，建议路径为：

```text
docs/LOCAL_MARKET_AGENT_MASTER_PLAN.md
```
