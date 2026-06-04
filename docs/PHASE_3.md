# 阶段三实施记录

## 完成范围

阶段三已完成“内容动态与预警闭环”：

```text
账号定时或手动采集
→ 发现和更新公开内容
→ 保存内容指标快照
→ 执行新内容与增长阈值规则
→ 生成站内预警
→ 尝试发送 Webhook 通知
→ 运营人员查看并处理预警
```

## 数据模型

- `content_posts`：保存发现的公开内容，使用 `creator_id + platform_content_id` 唯一约束防重。
- `content_snapshots`：记录每次采集时的点赞、评论、收藏和分享指标。
- `alert_rules`：保存新内容和增长阈值规则、启用状态与通知渠道。
- `alerts`：保存触发的预警、已读状态、通知状态和幂等键。

数据库迁移：

```text
687525cbdc3f_add_content_and_alert_monitoring.py
```

## 后端能力

- MockCollector 每次采集生成一条新内容，并返回最近三条内容的公开指标。
- 旧内容会更新指标并新增快照，同一平台内容不会重复保存。
- 默认创建“发现新内容”和“内容点赞增长”两条预警规则。
- 预警使用 `dedupe_key` 防止重复生成。
- 支持单条已读、全部已读、规则启停和增长阈值更新。
- 支持飞书、企业微信和通用 JSON Webhook。
- Webhook 失败不会导致采集任务失败，错误会保存在预警记录中。

## 前端能力

- 内容动态流：平台筛选、标题/创作者搜索、公开互动指标和内容链接。
- 内容详情抽屉：查看同一内容的历史指标快照。
- 预警中心：未读数量、类型筛选、通知状态和已读处理。
- 预警规则面板：规则启停和点赞增长阈值设置。
- 桌面端与移动端布局。

## 主要 API

```text
GET   /api/v1/posts
GET   /api/v1/posts/{post_id}
GET   /api/v1/posts/{post_id}/snapshots

GET   /api/v1/alerts
PATCH /api/v1/alerts/{alert_id}/read
PATCH /api/v1/alerts/read-all

GET   /api/v1/alert-rules
POST  /api/v1/alert-rules
PATCH /api/v1/alert-rules/{rule_id}
```

## Webhook 配置

在根目录 `.env` 中填写：

```dotenv
ALERT_WEBHOOK_URL=https://example.com/your-webhook
ALERT_WEBHOOK_TIMEOUT_SECONDS=5
```

配置后重启 FastAPI 与 Celery Worker。未配置地址时，预警的通知状态为 `skipped`。

## 当前限制

- 公开内容仍由 MockCollector 生成，真实平台数据属于阶段四。
- 暂未接入公开评论，评论监控与运营分析属于阶段五。
- Webhook 通知目前为同步短超时发送，生产环境可进一步拆分为独立通知任务。
