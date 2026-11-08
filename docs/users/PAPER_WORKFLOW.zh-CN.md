# 模拟交易审批流程

[English](PAPER_WORKFLOW.md) · [用户指南](README.zh-CN.md)

默认流程：研究 → 风控 → 生成交易意图 → 明确审批 → 执行前复查 → 模拟成交。`paper-log` 现在生成待审批意图并返回 `pending_manual_approval`，不再直接成交。静态 2026 示例属于历史数据，今天直接导入后被拒绝是正确行为。

使用有效的当前数据运行 `phase7-run-daily`，通过 `paper-status --db PATH` 查看意图。审核市场、方向、数量、限价、模拟成交价、费用、证据和风险决定，再运行：

```bash
lma paper-approve --intent-id INTENT_ID --actor YOUR_NAME --reason '已核对证据和模拟风险' --expires-seconds 300 --db PATH
lma paper-execute --intent-id INTENT_ID --db PATH
```

对尚未执行的意图，可用 `paper-approve --reject` 拒绝或撤销；最后一条审批记录生效。默认有效期 300 秒，可设为 1–3600 秒。意图、行情、研究简报、信号、风险决定或风控配置发生变化后，必须生成新意图。审批不能覆盖市场状态、证据、时效或风险限制。执行复查和账本写入在同一事务中完成；重试返回原订单，不重复成交。

`--no-require-manual-approval` 仅适用于明确的本地 fixture/history 模拟，仍生成逐意图的 `local-simulation` 审批凭据，不能称为人工审批或盈利证据。公开数据运行始终需要明确审批。底层账本默认不再允许直接开仓；业务使用 `PaperExecutionService`，`simulation_only=True` 仅允许 fixture 账本测试。

本地审核人名称是审计标签，不是身份认证。本项目面向可信的单用户本地环境，不是多用户授权服务。内容哈希用于检查变更，拥有数据库写权限的人仍可重写记录，不声称密码学防篡改。

UTC 日初权益采用上一个交易日最后一次有效观察值，第一次从初始资金建立基线；峰值是有效观察中的最大值，不是假定连续监测得到的市场峰值。执行时所有未平持仓都必须有新鲜有效报价。拒绝的行情不更新风控历史；回溯运行需使用独立数据库。

审批/执行命令输出 JSON：退出码 `0` 表示审批成功或执行完成，`3` 拒绝，`4` 等待审批，`5` 风险熔断；参数错误为 `2`，异常失败为非零。待审批和拒绝均不等于已成交。
