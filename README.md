# n8n 信息聚合器 v2 · GitHub Actions

仓库以 `n8n/workflow.template.json` 保存 v2 工作流，由 GitHub Actions
临时启动固定版本 n8n、注入 Secrets、执行一次工作流。工作流中的
Schedule Trigger 不负责 GitHub 定时，GitHub Actions 的 cron 才是调度器。

## 运行方式

- `dry-run`：最多处理 3 条资讯；跳过飞书发送、飞书多维表格和推送记录写入。
- `publish`：执行完整工作流，写入 Data Table、发送飞书卡片并写入待观察多维表格。
- 手动运行默认 `dry-run`；每天北京时间 09:00 的定时运行使用 `publish`。
- 定时推送默认关闭；完成手动 `dry-run` 和 `publish` 验证后，再设置仓库变量
  `PUBLISH_ENABLED=true` 启用。
- v2 的 Data Table 状态通过 GitHub Actions Cache 跨运行保存。

## 必须配置的 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 用途 |
|---|---|
| `N8N_ENCRYPTION_KEY` | n8n 本地数据库和凭证的稳定加密密钥 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook 完整地址 |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_BITABLE_APP_TOKEN` | 待观察多维表格 App Token |
| `FEISHU_BITABLE_TABLE_ID` | 待观察多维表格 Table ID |

`N8N_ENCRYPTION_KEY` 必须是固定的随机值且以后不能随意更换，否则已缓存的
n8n 凭证将无法解密。不要在仓库或聊天中提交任何真实密钥。

## 首次上线顺序

1. 配置以上 Secrets。
2. 在 Actions 中手动运行 `n8n information aggregator v2`，模式选 `dry-run`。
3. 检查运行摘要、DeepSeek 结果和错误日志。
4. 确认无误后，再手动运行一次 `publish`。
5. 在 **Settings → Secrets and variables → Actions → Variables** 中添加
   `PUBLISH_ENABLED=true`，启用每天 09:00 的定时任务。

首次运行会自动创建名为 `已推送记录` 的 Data Table，列结构是
`link`、`title`、`pushed_at`。后续运行会从 Actions Cache 恢复该状态。

## 日常维护

- 修改固定资讯源：编辑 `config/sources.json` 的 `rss_nodes`。
- 增加任意多条 RSS：把 `{ "url": "...", "source": "来源名" }` 加入
  `extra_feeds`，运行时会自动生成输入并只启用这一个补充源分支。
- 增删标签规则：编辑 `config/tag-rules.json`。
- 修改 AI 分类任务：编辑 `config/prompts/ai-classify.txt`。
- 修改语言深度解析任务：编辑 `config/prompts/language-analysis.txt`。
- 增加新的 RSS 节点或改动工作流连接：在 n8n 中更新后重新导出
  `n8n/workflow.template.json`。

`extra_feeds` 为空时，运行时会自动移除 `补充源 RSS` 的空分支。

## 重要限制

- GitHub 的定时任务可能有几分钟到十几分钟延迟。
- 新的固定分支如果需要在固定来源之外改变连接逻辑，仍需在 n8n 中更新并重新导出模板。
- Actions Cache 不是永久数据库。长期停跑后缓存可能被回收，届时查重历史会重新建立。
- n8n 工作流升级后，必须重新做一次 `dry-run`，确认社区飞书节点和 Data Table 仍兼容。
