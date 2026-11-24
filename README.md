# n8n 信息聚合器 v2 · GitHub Actions

## 先看这里：这个设计到底是不是你要的

它适合“每天定时抓取、分类，然后推送飞书”：

1. GitHub Actions 按计划临时启动一个 n8n。
2. 自动导入本仓库中的 v2 工作流。
3. 运行一整次工作流。
4. 推送成功后销毁临时 n8n。
5. 下一次运行再从 Actions Cache 恢复查重用的 Data Table。

它不是一台永久在线、随时能打开网页编辑的 n8n 服务器。如果你要的是
“每天跑一次”，这个设计符合要求；如果你要的是“GitHub 上一直有一个 n8n
网页可以访问”，GitHub Actions 不适合，需要把 n8n 部署到服务器、Docker
或支持常驻服务的平台。

工作流里的 `Schedule Trigger` 不负责实际定时。真正的定时器是
`.github/workflows/n8n-v2.yml` 里的 cron：

```yaml
- cron: "0 1 * * *"
```

这是 UTC 01:00，也就是北京时间每天 09:00。

## 两种运行模式

- `dry-run`：最多处理 3 条资讯；跳过飞书发送、飞书多维表格和推送记录写入。
- `publish`：执行完整工作流，写入 Data Table、发送飞书并写入待观察多维表格。

手动运行默认是 `dry-run`。定时运行固定使用 `publish`，但默认关闭，必须
完成两次手动测试后才会启用。

## 第一步：先添加 2 个 Secrets

打开：

<https://github.com/shawstone/n8n-actions/settings/secrets/actions>

点击 **New repository secret**，逐个添加。名称必须完全一致。

| 第一次测试必需 | 填什么 |
|---|---|
| `N8N_ENCRYPTION_KEY` | 一段固定的随机字符串 |
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API Key |

生成 `N8N_ENCRYPTION_KEY` 可以在 PowerShell 中执行：

```powershell
[Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLower()
```

生成后复制到 GitHub Secret。以后不要随意更换，否则缓存的 n8n 凭证无法解密。
不要把这个值发到聊天里。

## 第二步：合并 PR，再手动跑 dry-run

1. 打开项目 PR，确认文件无误。
2. 点击 **Ready for review**，再点击 **Merge pull request**。
3. 进入仓库的 **Actions** 页面。
4. 左侧选择 **n8n information aggregator v2**。
5. 点击右侧 **Run workflow**。
6. 分支选 `main`，mode 选 `dry-run`。
7. 再次点击绿色的 **Run workflow**。
8. 等待任务从黄色变成绿色，通常需要几分钟到二十分钟。
9. 打开本次运行页面，底部可以下载 `n8n-v2-summary-...` 摘要。

`dry-run` 会真实调用 DeepSeek，但不会发飞书，也不会修改推送记录。

如果失败，打开失败步骤的日志，优先找第一条 `Error` 或
`Required GitHub Actions secret is missing`。不要截图包含密钥的长日志。

## 第三步：添加飞书 Secrets，再跑 publish

dry-run 通过后，回到
<https://github.com/shawstone/n8n-actions/settings/secrets/actions>，
再添加这 5 个 Secret：

| 正式发布必需 | 从哪里获得 |
|---|---|
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 Webhook 的完整 URL |
| `FEISHU_APP_ID` | 当前版本暂不使用，可为以后多维表格保留 |
| `FEISHU_APP_SECRET` | 当前版本暂不使用，可为以后多维表格保留 |
| `FEISHU_BITABLE_APP_TOKEN` | 当前版本暂不使用，可为以后多维表格保留 |
| `FEISHU_BITABLE_TABLE_ID` | 当前版本暂不使用，可为以后多维表格保留 |

然后进入 **Actions → n8n information aggregator v2 → Run workflow**，
选择 `main` 和 `publish`。确认飞书实际收到内容，并且多维表格可以写入。

## 第四步：启用每天 09:00 定时运行

打开：

<https://github.com/shawstone/n8n-actions/settings/variables/actions>

点击 **New repository variable**，添加：

- Name：`PUBLISH_ENABLED`
- Value：`true`

在你添加它之前，即使到了 09:00，定时任务也会跳过。添加后，下一次
北京时间 09:00 会正式运行 `publish`。

## 在 GitHub 网页里补充资讯源

打开：

<https://github.com/shawstone/n8n-actions/blob/main/config/sources.json>

点击右上角铅笔图标。找到 `extra_feeds`，现在是：

```json
"extra_feeds": [
  {
    "url": "",
    "source": ""
  }
],
```

填写一个 RSS：

```json
"extra_feeds": [
  {
    "url": "https://example.com/feed.xml",
    "source": "示例来源"
  }
],
```

填写多个 RSS：

```json
"extra_feeds": [
  {
    "url": "https://example.com/one.xml",
    "source": "来源一"
  },
  {
    "url": "https://example.com/two.xml",
    "source": "来源二"
  }
],
```

注意 JSON 使用英文双引号；两个对象之间要有英文逗号；最后一个对象后面
不要多写逗号。修改后点击 **Commit changes**。

空白的 `url` 和 `source` 会被忽略，所以暂时不补充也没关系。下一次运行
Actions 时会自动读取，不需要重新导入 n8n。

## 在 GitHub 网页里补充标签规则

打开：

<https://github.com/shawstone/n8n-actions/blob/main/config/tag-rules.json>

文件末尾已经留了一个空对象：

```json
{
  "label": "",
  "pattern": ""
}
```

例如补充“新能源”标签：

```json
{
  "label": "新能源",
  "pattern": "新能源|电池|光伏|储能"
}
```

`label` 是标签名称，`pattern` 是标题中包含的关键词。`|` 表示“或者”，
标题命中其中任意一个词就会打上该标签。

增加多个规则时，在末尾继续增加对象：

```json
{
  "label": "机器人",
  "pattern": "机器人|具身智能|人形"
},
{
  "label": "新能源",
  "pattern": "新能源|电池|光伏|储能"
}
```

空对象会被忽略。填完后点击 **Commit changes**。

## 修改 AI 任务提示词

在 GitHub 网页中直接编辑：

- `config/prompts/ai-classify.txt`
- `config/prompts/language-analysis.txt`

修改并提交后，下一次 Actions 运行会自动使用新提示词。

## 飞书多维表格

“待观察”数据不再经过社区节点，而是由 GitHub Actions 使用飞书官方 API
写入。当前多维表格只有一列 `文本`，每条记录会整理成：

```text
标题：...
来源：...
日期：...
标签：...
链接：...
```

字段映射在 `config/feishu-bitable.json`。以后多维表格增加独立字段后，可以
把 `single_text_field` 删除，改为使用 `field_map` 写入多列。

可以先运行 **Feishu Bitable field check**，勾选 `write_test=true` 写入一条
带“测试记录”字样的数据，验证应用权限和表格结构。

## GitHub Pages 与 R2

`publish` 成功后会自动生成并部署网页：

<https://shawstone.github.io/n8n-actions/>

`dry-run` 只生成页面文件放进 Actions Artifact，不会覆盖线上页面。

如需同时备份到 Cloudflare R2，添加以下 Secrets；未配置时会自动跳过：

| R2 Secret | 用途 |
|---|---|
| `R2_ACCESS_KEY_ID` | R2 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | R2 Secret Access Key |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `R2_BUCKET` | 存储桶名称 |

备份路径为 `n8n-v2/latest/` 和按北京时间分目录的历史快照。

## 常见问题

`Required GitHub Actions secret is missing`

说明 Secret 名称拼错或该 Secret 没有添加。名称必须和上面的表格完全一致，
区分大小写。

`n8n workflow execution failed`

打开本次运行日志，查看最靠前的错误。常见原因是 RSS 临时不可访问、
DeepSeek Key 失效、飞书权限不足，或飞书 Token/Table ID 填错。

为什么运行后有几分钟到二十分钟延迟？

GitHub 的免费定时器不保证精确到分钟，而且每次都要启动 Docker、安装飞书
社区节点并导入工作流。建议接受 10 到 30 分钟的运行窗口。

为什么没有永久的 n8n 编辑页面？

GitHub Actions 的运行环境会在任务结束后销毁。项目用 Actions Cache 保存
查重表状态，但没有常驻的 n8n 编辑器。如果长期停止运行，缓存可能被回收，
查重历史会重新开始。
