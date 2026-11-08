# 证据包与结算

[English](EVIDENCE_PACKETS.md) · [审批流程](PAPER_WORKFLOW.zh-CN.md)

先用一个市场的小证据包验证真实数据流程，再扩大实验。证据包是本地 JSON，包含行情快照、证据、来源凭据、结算来源地址，可选研究简报和结算结果。工具不抓取任意链接，也不调用模型。证据包和来源文件放在同一目录。

来源凭据包含 `source_id`、公开 `url`、相对 `path`、SHA-256、`retrieved_at` 和可选 `published_at`。每条证据的 `metadata.source_id`、URL 和时间必须对应来源凭据；发布时间和采集时间都必须不晚于行情快照。事后搜到一篇文章不代表当时已取得它。来源路径不可越出证据包目录。简报必须使用完全一致的已审核证据及结算来源。`packet-check` 分别展示来源有效性和缺少流动性、数据过期、缺少简报等执行阻断原因。

```bash
lma packet-check --packet packet/packet.json
lma packet-review --packet packet/packet.json --output packet/research-review.json --actor YOUR_NAME --reason '已核对来源含义、时间和结算规则'
lma packet-prepare --packet packet/packet.json --review packet/research-review.json --db data/experiment.sqlite
```

生成意图后返回退出码 4 和意图 ID，随后按[审批流程](PAPER_WORKFLOW.zh-CN.md)逐条审批并执行。证据审核不等于订单审批。简报中的概率估计需有依据，不会为了让真实样本通过而补造数值。审核凭据绑定包内容哈希、审核人标签、理由、用途和时间；本地标签不提供身份认证。哈希不能证明摘要忠实于原文，该判断仍需审核人完成。

结算时创建新证据包，保留原证据文件。提供 settled 状态的快照和 `settlement`：市场 ID、`yes`/`no` 结果、来源 ID、最终结果时间。结算来源必须符合市场规则，可能与预报提供方不同。

```bash
lma packet-review --packet packet/settlement-packet.json --output packet/settlement-review.json --scope settlement --actor YOUR_NAME --reason '已核对最终公布的结算结果'
lma packet-settle --packet packet/settlement-packet.json --review packet/settlement-review.json --db data/experiment.sqlite
lma paper-replay --intent-id INTENT_ID --db data/experiment.sqlite
```

平仓成交和来源/审核凭据在同一事务写入。相同证据包重试不重复平仓，冲突结算包会被拒绝；已在账本结算的市场不能通过执行服务重新开仓。历史文件沙盒的结算功能仍属于本地模拟。

隔离演示会生成完整可查看的示例证据包；其中审核凭据明确标记为合成演示，不是对公开市场证据的人工审核。真实样本字段不完整时继续阻断，这也是有效验证结果。公开原始响应保留为本地生成产物，不作为内置市场数据集发布。
