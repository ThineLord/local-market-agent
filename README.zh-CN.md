# Local Market Agent

[English](README.md) · [简体中文](README.zh-CN.md)

**用户入口：** 从[用户指南](docs/users/README.zh-CN.md)开始。

**Agent 入口：** 先读 [AGENTS.md](AGENTS.md)，再读 [Agent 指南](docs/agents/README.zh-CN.md)。

Local Market Agent 将**公开市场快照 → 研究简报 → 风险检查 → 明确审批 → 模拟交易 → 本地报告**串成可检查的工作流。项目基于 Python，优先支持离线使用，提供确定性示例数据和本地仪表板，便于检查证据、验证纸面交易流程。

**仅限模拟交易。** 这是实验性研究工具。示例结果不能证明策略盈利能力或生产可用性。

## 本地启动

需要 **Python 3.11 或更新版本**。在仓库根目录运行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
lma watchlist-screen --as-of 2026-06-05T00:02:00Z
python ui/server.py
```

打开 **http://127.0.0.1:8502/#watchlist/screening**。合成示例不需要 API 密钥，也不会请求市场数据。固定时间用于匹配历史示例；按当前时间检查时，旧数据会被正确标为过期。端口占用时可运行 `python ui/server.py --port 8503`。

## 三步使用

1. **检查观察列表。** 对比市场快照、证据缺口和阻断原因。
2. **审核并批准具体意图。** 按[审批流程](docs/users/PAPER_WORKFLOW.zh-CN.md)操作；LLM 只能生成研究内容。
3. **查看审计记录。** 在本地只读仪表板中查看报告与模拟记录。

独立的[香港赛马工作区](docs/HORSE_REPLAY.zh-CN.md)支持历史记录回放及原始赛前快照核验。缺失证据保留 UNKNOWN，当前赛马研究输出 NO BET。

## 文件位置

```text
src/local_market_agent/   Python 包与命令行入口
ui/                      本地仪表板与 Streamlit 界面
data/fixtures/           纳入版本控制的确定性示例
data/                    Git 忽略的本地数据库与生成结果
tests/                   离线测试及可选网络测试
scripts/                 版本检查与本地研究工具
docs/users/              中英文用户指南
docs/agents/             中英文 Agent 指南
docs/releases/           各版本发布说明
docs/archive/            历史阶段计划与审查记录
```

## 文档与版本

- [中文用户指南](docs/users/README.zh-CN.md) · [English user guide](docs/users/README.md)
- [中文 Agent 指南](docs/agents/README.zh-CN.md) · [English Agent guide](docs/agents/README.md)
- [文档索引](docs/README.md) · [安全与风控](docs/SAFETY_AND_RISK.md)
- [变更记录](CHANGELOG.md) · [版本管理规则](docs/VERSIONING.zh-CN.md)
- [0.5.0 发布说明](docs/releases/0.5.0.zh-CN.md) · [GitHub Releases](https://github.com/ThineLord/local-market-agent/releases)

当前应用版本为 **0.5.0**。后续发布统一使用一致的包版本、`vX.Y.Z` 标签、发布说明和经过审查的 PR。Codex 负责组织与管理，subagents 负责 review 和合并，不委派 bots。

默认保持 `REAL_MONEY_ENABLED=false`、`ALLOW_LIVE_ORDERS=false`、`HUMAN_APPROVAL_REQUIRED=true`。每笔模拟订单必须关联信号和已批准的风险决策。可运行[完整隔离演示](docs/users/README.zh-CN.md#新审批与证据流程)。升级方式和剩余限制见发布说明。
