# 阶段二实施记录

## 完成范围

阶段二已完成“指定账号基础监控闭环”：

```text
添加账号
→ MockCollector 首次采集
→ 保存账号公开指标
→ 保存历史快照
→ 手动或定时再次采集
→ 前端展示账号状态与趋势
```

## 后端能力

- 核心数据表：`creator_accounts`、`creator_snapshots`、`collection_runs`。
- Alembic 迁移：`0da7d4157c5f_create_creator_monitoring_tables.py`。
- 账号管理 API：创建、列表、详情、更新、删除。
- 数据采集 API：立即采集和快照查询。
- MockCollector：生成稳定递增的账号公开指标。
- Celery Worker：执行单账号采集任务。
- Celery Beat：每分钟扫描一次到期账号。

## 前端能力

- 监测总览：账号数、覆盖粉丝、累计获赞、最近采集。
- 账号列表：搜索、平台筛选、状态筛选和分页。
- 账号操作：添加、编辑、暂停、恢复、立即采集和删除。
- 账号详情：公开资料、指标概览、趋势图和历史快照。
- 支持桌面端与移动端布局。

## 主要 API

```text
POST   /api/v1/creators
GET    /api/v1/creators
GET    /api/v1/creators/{creator_id}
PATCH  /api/v1/creators/{creator_id}
DELETE /api/v1/creators/{creator_id}
POST   /api/v1/creators/{creator_id}/collect
GET    /api/v1/creators/{creator_id}/snapshots
```

## 当前限制

- 当前只使用 MockCollector，不访问真实平台。
- 内容动态、评论和预警属于阶段三范围。
- 后台播放量、曝光量等数据仍需要平台授权。
