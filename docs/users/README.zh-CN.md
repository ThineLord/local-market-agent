# 用户指南

[English](README.md) · [简体中文](README.zh-CN.md) · [项目首页](../../README.zh-CN.md)

Local Market Agent 用于公开数据研究、风险检查和模拟交易。它优先支持离线示例；实盘交易、提款、杠杆、衍生品、做空、私有交易接口以及 LLM 直接下单均不在项目范围内。历史审查中仍有流程限制，详见[发布说明](../releases/0.2.0.zh-CN.md)。

## 安装

使用 Python 3.11 或更新版本，在仓库根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

以下命令均在根目录、已激活环境中运行。安装依赖需要网络，示例工作流本身可离线运行。

## 离线工作流

以下操作会写入本地研究、风险和报告记录；符合规则时也可能写入模拟订单。保留安全默认值；信号被阻断时不会保证产生成交。

```bash
export LMA_LLM_PROVIDER=mock
lma ingest-demo
lma generate-brief --fixture data/fixtures/demo_market.json
lma risk-check
lma paper-log
lma report-daily
```

示例使用确定性数据和 mock 模型，无需 API 密钥。数据库、研究简报和运行报告通常写入 `data/`，不要提交这些本地数据、导出文件或凭证。

## 观察列表与仪表板

```bash
lma watchlist-screen --as-of 2026-06-05T00:02:00Z
python ui/server.py
```

打开 **http://127.0.0.1:8502/#watchlist/screening**。一次可筛查 1–50 个市场，搜索、筛选、查看检查项和输入哈希，或导出 CSV。示例包含候选、缺少研究、价差过宽、缺少卖价和过期快照。固定时间用于历史合成示例；不传 `--as-of` 时，旧快照会被标为过期。

每次结果保存在 `data/reports/watchlist/screen-<id>/report.json` 与 `report.md`；`latest.json` 提供最新结果。筛查不使用 LLM、不打开交易数据库、不批准证据，也不创建订单。研究候选仍须经过后续风险审查与相应人工审批流程。输入格式、可选 Kalshi/Polymarket 公开快照和限制见[观察列表说明](../WATCHLIST_SCREENING.md)。

仪表板仅监听回环地址，以只读方式读取 SQLite；没有数据库时会明确显示示例预览。端口占用时使用 `python ui/server.py --port 8503`。界面支持记录搜索、排序、筛选、CSV 导出、详情抽屉、证据/反证、审计关联，以及 Light、Dark、System 外观模式。背景动画可暂停，并遵循系统减少动态效果设置。

主要类别最多加载 500 条记录，同时显示总数；Phase 7 视图保留 25 个运行 / 100 条执行记录的限制。价格和时间是已保存的观测，不是实时行情。设置采用只读允许列表；刷新仅重读本地数据，不触发采集。界面没有下单或审批接口。窄屏使用可折叠导航和独立表格滚动。前端资源在本地渲染，无需前端构建或远程资源。

原 Streamlit 界面仍可使用：

```bash
streamlit run ui/app.py
```

## 研究模型

默认提供方为离线、确定性且无需密钥的 `mock`：

```bash
lma llm-provider-audit
```

需要本地或兼容 OpenAI 接口的研究模型时，显式配置端点与模型：

```bash
export LMA_LLM_PROVIDER=openai-compatible
export LMA_OPENAI_COMPATIBLE_BASE_URL=http://localhost:1234/v1
export LMA_OPENAI_COMPATIBLE_MODEL=local-model
export LMA_OPENAI_COMPATIBLE_API_KEY=optional-local-key
lma phase7-run-daily --llm-provider openai-compatible --llm-model local-model
```

密钥仅通过本地环境或配置传入，不要写入代码或提交到 Git。外部端点会收到研究请求，使用前确认数据范围和费用授权。LLM 只能生成研究 JSON；信号、风险决策和模拟订单仍由规则控制。

## 市场数据与历史回放

默认使用确定性示例：

```bash
lma market-data-audit
lma phase7-run-daily --market-source fixture
```

公开只读数据源需要显式选择，并会访问网络：

```bash
lma phase7-run-daily --market-source polymarket --market-id <market-id>
lma phase7-sandbox-run --days 30 --market-source yfinance --market-id SPY
```

非示例快照的沙盒运行重复使用当前快照，只验证流程，不是历史盈利回测，也不会执行实盘交易。

本地历史 JSONL 可按日期回放：

```bash
lma phase7-sandbox-run   --market-source historical-file   --historical-file data/fixtures/phase7_historical_5d.jsonl   --days 5
```

该模式仅读取本地文件。结算/结果数据支持基于结果的评估，但不能单凭其存在证明策略盈利；还需考虑证据质量和历史数据限制。

## 检查与安全边界

```bash
ruff check .
pytest
python scripts/check_release.py
```

网络测试带有 `network` 标记，默认跳过，只有显式设置 `LMA_RUN_NETWORK_TESTS=true` 才启用。

- `REAL_MONEY_ENABLED=false`
- `ALLOW_LIVE_ORDERS=false`
- `HUMAN_APPROVAL_REQUIRED=true`
- 每笔模拟订单必须关联信号与已批准的风险决策。
- LLM 不得创建订单；风险规则检查证据、置信度、价差、优势和禁用交易行为。

历史审查记录不等于当前验收。后续开发及发布请遵循 [Agent 指南](../agents/README.zh-CN.md)和[版本规则](../VERSIONING.zh-CN.md)。
