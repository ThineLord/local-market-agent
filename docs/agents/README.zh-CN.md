# Agent 指南

[English](README.md) · [简体中文](README.zh-CN.md) · [项目首页](../../README.zh-CN.md)

先读根目录 [AGENTS.md](../../AGENTS.md)。Codex 负责统筹、文件组织、实现和发布准备；subagents 独立审查最终改动，并在验证通过后执行合并。不要委派 bots 或调用外部 bot bridge。subagent 的审查不自动等于 GitHub 的 APPROVED review，汇报时须说明实际审查方式。

## 开始工作

1. 查看工作区、分支、远程默认分支、未合并 PR 和最新版本。保留无关改动与本地数据，必要时使用隔离副本。
2. 阅读[用户指南](../users/README.zh-CN.md)、[安全规则](../SAFETY_AND_RISK.md)和[版本规则](../VERSIONING.zh-CN.md)。
3. 将[阶段归档](../archive/README.md)和[报告](../reports/)视为有日期的历史证据。[实施日志](../IMPLEMENTATION_LOG.md)保留工作过程，不代表全部功能已验收。
4. 在 `codex/` 分支上进行范围一致的改动，不把无关 PR 混入，也不要因整理而关闭它们。

## 文件归属

| 位置 | 用途 |
| --- | --- |
| `src/local_market_agent/` | 运行包、适配器、研究、风控、模拟账本与 CLI |
| `ui/` | 回环地址仪表板、静态资源和 Streamlit 界面 |
| `tests/` | 确定性离线测试，以及显式启用的网络测试 |
| `data/fixtures/` | 提交到仓库的合成示例与验证数据 |
| `data/` | 本地数据库及生成数据；多数运行输出已忽略 |
| `scripts/local_only/` | 研究工具；执行前检查网络访问和输出行为 |
| `docs/users/`、`docs/agents/` | 分开的中英文用户与 Agent 入口 |
| `docs/releases/` | 按版本保存的发布说明 |
| `docs/archive/`、`docs/reports/` | 历史设计/审查，以及既有命令使用的报告路径 |

除非明确包含迁移工作，否则保持运行路径稳定。不提交 `.env`、数据库、cookies、密钥、浏览器数据或私有原始导出。`.env.example` 仅放占位符，不得填入真实凭证。

## 安全要求

仓库仅限模拟交易。不得加入实盘订单、私有交易接口、提款、杠杆、衍生品、做空、地理限制绕过或 LLM 直接下单路径。保持默认值：

```text
REAL_MONEY_ENABLED=false
ALLOW_LIVE_ORDERS=false
HUMAN_APPROVAL_REQUIRED=true
```

每笔模拟订单必须关联信号与已批准的风险决策。模型输出仅用于研究，不构成下单授权。示例保持确定性，网络测试必须可选并带 `network` 标记；检查文档时不要顺带启用网络采集或付费模型。

## 验证、审查与合并

在仓库根目录、已激活的 Python 3.11+ 环境运行：

```bash
ruff check .
pytest
python scripts/check_release.py
git diff --check
```

创建 draft PR 前，将实际结果和限制记入 `docs/IMPLEMENTATION_LOG.md`。仅按改动需要增加针对性检查。移动文档时检查相对链接与两种语言内容；保持版本、发布说明及变更记录一致。

review subagent 检查最终 diff、验证证据和对应 head commit 的 CI。问题修复后，由 subagent 将 PR 标为 ready，并以预期 head SHA 保护执行合并。如果分支规则要求当前账号无法提供的独立 GitHub approval，应报告阻塞，不绕过规则，也不将建议性审查称为正式批准。

合并后，Codex 验证合并提交，依照[版本规则](../VERSIONING.zh-CN.md)发布版本标签与 GitHub Release，再核实链接。合并授权不扩展到无关 PR、数据采集或实盘交易。
