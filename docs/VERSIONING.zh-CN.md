# 版本管理

[English](VERSIONING.md) · [简体中文](VERSIONING.zh-CN.md)

**0.2.0** 是第一个纳入本流程管理的 GitHub Release。此前代码声明版本为 `0.1.0`，没有已发布的 Release；不补造或倒填历史发布。

## 版本边界

应用版本采用 `主版本.次版本.修订版本`，Git 标签采用 `vX.Y.Z`。1.0 之前，次版本可调整工作流，但必须说明迁移；修订版本用于兼容的修复与文档更正。1.0 之后，公开 CLI 或数据契约的不兼容变动必须增加主版本。数据 schema 使用独立标识，不得为匹配应用版本而静默迁移本地数据库。

`pyproject.toml` 与 `src/local_market_agent/__init__.py` 必须一致，两份首页显示同一版本。每次发布在 `docs/releases/X.Y.Z[.zh-CN].md` 保存中英文说明，并更新 `CHANGELOG.md`。尚未发布的工作先记入 Unreleased；发布 PR 再统一完成版本提升与说明。

## 发布步骤

1. 从最新 `main` 建立 `codex/` 分支，仅纳入本次计划发布且经过审查的工作，列出重要未解决限制与排除项。
2. 更新两个版本声明、两份首页、变更记录、中英文发布说明和实施日志，说明文件或数据迁移。
3. 创建 draft PR 前运行 `ruff check .`、`pytest`、`python scripts/check_release.py --tag vX.Y.Z`、`git diff --check`，检查暂存文件中是否存在凭证或本地数据。
4. 由 subagent 审查最终 diff 和实际验证结果，修复问题，并确认最终 head 的 CI 通过后，将 PR 标为 ready，以预期 head SHA 保护执行合并。不调用 bots，不绕过分支规则。
5. 拉取 `main`，确认 PR 已合并并确定准确的 merge SHA。在该提交验证版本与标签一致性，并等待对应合并提交的 CI 成功。
6. Codex 在该 merge SHA 创建带注释的 `vX.Y.Z` 标签，仅推送该标签，然后从 `docs/releases/X.Y.Z.md` 发布 GitHub Release。命令为 `gh release create vX.Y.Z --verify-tag --title "Local Market Agent X.Y.Z" --notes-file docs/releases/X.Y.Z.md`。不上传数据库、原始导出、凭证或环境目录。
7. 核验发布链接、标签目标、版本声明和标签 CI，报告版本及主要限制。

CI 会在分支、PR 和 `v*` 标签上执行版本一致性检查；标签构建额外验证标签与包版本一致。发布由统筹者显式执行，不使用自动 bot 合并或发布。已发布标签不可强制移动；修正使用新的修订版本。回滚代码也应通过审查后的 PR，并发布新版本。
