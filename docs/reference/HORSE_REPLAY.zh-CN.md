# 香港赛马研究与历史回放

[English](HORSE_REPLAY.md) · [用户指南](../users/README.zh-CN.md)

本模块与原有市场并行，独立展示 HKD 历史账，不修改交易数据库、不生成模拟或真实订单。私人投注记录、原始快照和报告保存在被 Git 忽略的本地 `data/` 中。仓库示例全部为合成数据。

## 核对历史记录

```sh
PYTHONPATH=src python scripts/horse_replay.py collect --date YYYY-MM-DD --course ST --races 9 --output data/horse/official --allow-network
PYTHONPATH=src python scripts/horse_replay.py replay --record data/horse/user-history.json --official data/horse/official --output data/horse/replay
python ui/server.py --horse-workspace data/horse --port 8510
```

日期必须是已过去的比赛日，场次数应与完整官方声明一致，输出目录必须新建。采集仅请求每场公开赛果及完整出马表，保存原始响应、准确 URL、实际获取时间和 SHA-256；离线回放复核会议、场次、马号身份、派彩池完整性及来源时间。事后下载的出马表即使 URL 写着 `prerace`，也不是原始赛前可用性证明。

记录必须从 R1 连续覆盖整晚，包括明确的未下注或 UNKNOWN 场次。`NOT_PLACED` 表示没有记录实际投注，不代表失败投注，也不代表模型当时推荐了 NO BET。票据是否真实、原始推荐及兑奖事实需要各自证据。

显示三个独立金额：当时暂计派彩、按官方结果推算的应得派彩、有凭据引用的已兑奖现金。没有兑奖凭据时显示 UNKNOWN，不能填零。HKJC 标准每 HK$10 派彩包含本金，不能重复加回。自动核算仅支持整单位、正常名次且字段完整的 WIN/PLACE；退赛、替补、并头、退款等情况转人工复核。位置资格依据开售时声明参赛数和官方中奖组合，不能用赛后完赛马匹数替代。

统计区分票数与实际下注场数，并列出 WIN/PLACE 命中率、投注额、派彩、净收益、按投注额计算的 ROI、初始资金回报和逐场收盘应得权益最大回撤。曲线不是场内现金回撤，官方应得派彩也不等于已兑奖。没有独立事前预算记录时，预算合规性 UNKNOWN；固定金额不能证明历史上没有追损。一晚、少量且同场相关的投注不能证明稳定优势。

## 导入原始 T−10 / T−3 快照

在 `data/horse/research/` 放入原文件和 `research.json`，结构见 `src/local_market_agent/horse_racing/research.py` 的 `ResearchInput`。记录当时已知的计划开赛时间、决策时间、所有参赛马身份、档位、负磅、骑师依据、此前赛绩，以及分别观察的 WIN/PLACE 赔率。赔率必须明确为含本金的十进制指示赔率；位置区间保留下界和上界。缺失值填 `null`，不得补造概率、赔率或原始理由。

每个来源分别记录实际捕获时间、声称可用时间、路径、哈希；导入时间由系统另记。`availability-review.json` 绑定输入及全部来源哈希，包含审核者、真实审核时间、理由和归档时间证据引用。自填时间或单个批准开关不是可信历史证据；哈希与人工审核只能绑定审查过程，无法密码学证明历史可用性。原文件与转录一致性仍需独立审查。

```sh
PYTHONPATH=src python scripts/horse_replay.py research --input data/horse/research --output data/horse/research-audit
# 可先运行明确标记的合成示例：
PYTHONPATH=src python scripts/horse_replay.py research --input data/fixtures/horse_research --output data/reports/horse-synthetic
```

双检查点相对当时已知计划时间采用明确的 ±60 秒窗口，赔率观察应在决策前 60 秒内且已捕获。检查缺失快照、未来赛绩、过期赔率、来源可用性、身份/退赛/计划时间变化、未知资料和事前预算证据。预算须在首次检查点前固定、不超过本金、每票 HK$10；没有追损或因盈利加码逻辑。这些是新研究输入检查，不改变原市场风控门槛。

全场对比首先展示源事实与同场地/距离赛绩描述，优势和劣势描述只基于已知名次；缺失名次不算落败。WIN/PLACE 原始概率、理由与方法单独保留，不能机械配对。未经验证的 `p × 赔率下界 − 1` 只是假设分析，不能作为推荐，指示赔率也不是锁定成交价。

**当前版本没有已验证的赛马概率模型，所有研究输出均为 NO BET，生成订单为零。** 原始快照尚缺时保留 UNKNOWN；历史推荐仍是 UNKNOWN，不用当前阻断结论回填。概率校准需原始概率序列和另行规定的验证方案，暂不计算。本版交付数据与回放基础，不把单次盈利包装成算法。
