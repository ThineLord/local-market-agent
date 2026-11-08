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

最终结算凭据的 URL 必须与 `resolution_source` 完全一致，采集时间必须不早于 `resolved_at` 且不晚于结算快照；已知发布时间也必须不早于结果时间。结果产生前的研究材料不能替代最终结算来源。


## 定位阻断原因

`lma packet-check --packet packet/packet.json --review packet/research-review.json` 可验证审核凭据是否对应包的确切内容。`valid` 仅表示来源完整性；`preflight_ready` 表示行情/简报硬性检查通过；`research_ready` 还要求匹配的研究审核与可行动策略。以上均不是组合风控批准或订单审批。`checks`、`research_review`、`strategy`、`blockers` 分别列出各阶段。`packet-check` 的退出码 0 只表示已检查有效证据包，不代表可以下单。

先写简报，再进行 `packet-review --scope research`；只有来源文件的包不能标记为简报已审核。没有可靠概率估计时，可以如实编写并审核 `observe` 简报，但仍不能形成交易意图。`packet-prepare` 保留真实策略/风险拒绝原因，拒绝时不会写入权益基线。准备阶段仍检查组合风险，执行阶段再次检查并要求独立的逐意图审批。

当前 Kalshi 流动性使用双方顶档可买容量中较小的美元值：`min(YES ask × YES ask size, (1 − YES bid) × YES bid size)`。这不是整簿流动性或成交量；缺少数据保持未知，实际容量过小仍被默认 100 美元门槛阻断。


### 重跑有界真实数据检查

```bash
python scripts/collect_public_weather_packet.py --market-id KXHIGHNY-26NOV09-T57 --output data/reports/public-weather-NEW --allow-network
lma packet-check --packet data/reports/public-weather-NEW/packet.json
# 阅读来源文件和观察简报后，再记录实际研究审核。
lma packet-review --packet data/reports/public-weather-NEW/packet.json --output data/reports/public-weather-NEW/research-review.json --actor YOUR_REVIEWER_LABEL --reason YOUR_ACTUAL_REVIEW_FINDINGS
lma packet-check --packet data/reports/public-weather-NEW/packet.json --review data/reports/public-weather-NEW/research-review.json
lma packet-prepare --packet data/reports/public-weather-NEW/packet.json --review data/reports/public-weather-NEW/research-review.json --db data/reports/public-weather-NEW/paper.sqlite
```

选择当前开放的 KXHIGHNY 日最高温市场；上面的日期示例会到期。采集器仅做六次公开只读 GET：系列规则、NWS 预报/观测、单页同事件市场列表、订单簿、最后采集具体市场。拒绝覆盖已有目录，也不支持其他系列。保存带哈希的 JSON 凭据及成稿前后诊断。明确区分 NWS 生成/观测时间和未经验证的首次发布时间。订单簿仅存档供核对，快照深度完全取自同一次市场响应及其采集时间。

自动生成的是**观察简报草稿**：概率为空，明确禁止交易，即使来源审核完成也不能产生订单。采集器不生成审核、审批或数据库。审核人应真正检查资料并如实标识身份；agent 来源审核不是人工订单审批。可信概率估计、足够深度和独立订单审批仍是分别满足的前提，不应为演示通过而补造。缺少前提时 `packet-prepare` 退出码 3 是真实预期结果。未决市场不编造结算。
