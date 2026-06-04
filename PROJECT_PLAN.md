# 抖音 / 小红书创作者监测系统总体规划

## 1. 文档目标

本文档用于指导“抖音 / 小红书创作者监测系统”从需求确认、技术搭建、MVP 开发、公开数据采集，到测试、部署和持续迭代的完整实施过程。

系统第一阶段的核心目标不是建设一个覆盖所有平台数据的大型分析平台，而是先完成以下业务闭环：

1. 用户输入或选择需要监控的抖音、小红书账号。
2. 系统按照设定频率持续检查账号公开数据。
3. 系统发现新作品、数据增长或异常变化。
4. 系统保存历史快照，并通过趋势图展示变化。
5. 系统根据规则生成预警，提醒运营人员及时跟进。

---

## 2. 项目定位与数据边界

### 2.1 项目定位

本系统是一个面向运营人员的“指定创作者账号持续监控平台”，主要用于：

- 监控竞品、达人、客户或自有账号的公开动态。
- 第一时间发现账号发布的新视频或新笔记。
- 持续记录粉丝数、点赞数、评论数、收藏数等公开指标。
- 分析账号与内容数据的增长趋势。
- 发现爆款内容、异常增长、停更、删帖等情况。
- 聚合公开评论，辅助运营人员发现用户需求和负面反馈。

### 2.2 第一阶段可监控的数据

具体字段以平台实际公开展示和采集能力为准。

#### 账号公开数据

- 平台名称。
- 平台账号 ID。
- 昵称、头像、简介、主页链接。
- 认证状态、IP 属地或地区。
- 粉丝数、关注数、获赞数。
- 公开作品数量。
- 最近发布时间。

#### 内容公开数据

- 内容 ID、标题、正文摘要、封面、内容链接。
- 发布时间、内容类型。
- 点赞数、评论数、收藏数、分享数。
- 公开话题标签。
- 公开评论及评论时间。

### 2.3 不能默认获取的数据

以下数据通常属于账号后台数据，不能假设可以通过公开页面获得：

- 曝光量。
- 完整播放量。
- 完播率。
- 平均播放时长。
- 流量来源。
- 粉丝画像。
- 转化与成交数据。

这些数据只能作为后续增强能力，通过账号本人授权、官方开放平台、运营后台导入或合规第三方数据服务接入。

### 2.4 数据采集合规原则

- 优先使用官方开放平台与账号授权。
- 公开数据采集模块必须可替换，不能与核心业务代码强绑定。
- 控制采集频率，避免对平台造成压力。
- 不采集非公开个人信息。
- 不绕过登录验证、访问控制或平台安全措施。
- 保留数据来源、采集时间与原始响应，便于审计。
- 正式商用前需确认目标平台服务协议及适用法律要求。

---

## 3. 总体技术方案

### 3.1 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 前端 | Vue3 + TypeScript + Vite | 管理后台 |
| UI 组件 | Element Plus | 表格、表单、弹窗、菜单 |
| 图表 | ECharts | 趋势图、排行、统计图 |
| 状态管理 | Pinia | 前端状态管理 |
| HTTP 请求 | Axios | 调用后端 API |
| 后端 | FastAPI | API 与业务逻辑 |
| ORM | SQLAlchemy 2 | 数据库访问 |
| 数据迁移 | Alembic | 管理数据库结构变化 |
| 参数校验 | Pydantic | 请求、响应和配置校验 |
| 数据库 | MySQL 8 | 保存业务数据与历史快照 |
| 缓存 / 队列 | Redis | 缓存与 Celery 消息队列 |
| 异步任务 | Celery | 执行监控、采集、计算和通知任务 |
| 定时调度 | Celery Beat | 定时创建监控任务 |
| 测试 | Pytest | 后端自动化测试 |
| 部署 | Docker Compose | 本地基础设施与正式部署 |

### 3.2 系统架构

```text
┌──────────────────────────────┐
│ Vue3 管理后台                 │
│ 账号、动态、趋势、预警、配置   │
└──────────────┬───────────────┘
               │ HTTP API
┌──────────────▼───────────────┐
│ FastAPI                       │
│ 权限、账号管理、查询、规则配置 │
└───────┬───────────┬──────────┘
        │           │
        │           └──────────────┐
┌───────▼──────┐            ┌──────▼──────┐
│ MySQL 8      │            │ Redis       │
│ 业务与快照数据│            │ 缓存与任务队列│
└──────────────┘            └──────┬──────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Celery Worker      │
                         │ 采集、分析、预警、通知│
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ 平台数据适配器      │
                         │ 抖音 / 小红书 / 导入│
                         └───────────────────┘
```

### 3.3 推荐项目目录

```text
TikTok_platform_monitoring/
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI 路由
│   │   ├── core/                # 配置、数据库、日志、安全
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic 请求和响应结构
│   │   ├── repositories/        # 数据库访问
│   │   ├── services/            # 业务逻辑
│   │   ├── collectors/          # 平台采集适配器
│   │   ├── tasks/               # Celery 任务
│   │   ├── alerts/              # 预警规则
│   │   ├── notifications/       # 飞书、企微、邮件通知
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── views/
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
├── deploy/
│   └── nginx/
├── scripts/
├── docs/
├── .env.example
├── docker-compose.dev.yml
├── docker-compose.yml
└── README.md
```

---

## 4. 核心业务模块

### 4.1 监控账号管理

- 通过主页链接、账号 ID 或手动信息添加账号。
- 选择平台：抖音或小红书。
- 设置账号分组、标签、负责人和备注。
- 设置监控级别和采集频率。
- 启用、暂停或删除监控。
- 手动触发一次立即检查。

### 4.2 动态监控

- 展示所有被监控账号的新内容。
- 按平台、账号组、发布时间和内容类型筛选。
- 标记新内容、爆款内容和已读状态。
- 查看内容指标的历史变化。

### 4.3 数据快照与趋势

- 定时保存账号数据快照。
- 定时保存重点内容数据快照。
- 展示粉丝、获赞、点赞、评论和收藏增长趋势。
- 支持近 24 小时、7 天、30 天和自定义时间范围。

### 4.4 评论监控

- 保存公开评论。
- 识别新增评论。
- 按关键词、账号、时间和情绪标签筛选。
- 标记高价值评论、负面评论和待回复评论。

### 4.5 预警中心

第一版建议支持以下预警规则：

- 账号发布新内容。
- 粉丝数在指定时间内增长超过阈值。
- 内容互动量超过账号历史平均值指定倍数。
- 评论数短时间明显增长。
- 账号超过指定天数未更新。
- 已记录内容疑似被删除或下架。
- 数据采集任务连续失败。

### 4.6 通知渠道

按实施优先级逐步接入：

1. 系统站内通知。
2. 飞书机器人或企业微信机器人。
3. 邮件。
4. 短信或其他渠道。

---

## 5. 核心数据模型

### 5.1 用户与权限

第一版可使用简单管理员账户，后续再增加团队权限。

```text
users
- id
- username
- password_hash
- role
- is_active
- created_at
- updated_at
```

### 5.2 监控账号

```text
creator_accounts
- id
- platform
- platform_account_id
- nickname
- profile_url
- avatar_url
- bio
- verified_info
- location
- group_id
- priority
- monitor_interval_minutes
- monitoring_status
- last_collected_at
- next_collect_at
- consecutive_failures
- created_at
- updated_at
```

需要建立的主要索引：

- `platform + platform_account_id` 唯一索引。
- `monitoring_status + next_collect_at` 任务查询索引。
- `group_id` 普通索引。

### 5.3 账号数据快照

```text
creator_snapshots
- id
- creator_id
- follower_count
- following_count
- total_like_count
- content_count
- captured_at
```

主要索引：

- `creator_id + captured_at` 联合索引。

### 5.4 内容

```text
content_posts
- id
- creator_id
- platform_content_id
- title
- summary
- content_type
- content_url
- cover_url
- published_at
- first_discovered_at
- latest_like_count
- latest_comment_count
- latest_collect_count
- latest_share_count
- status
- raw_data_json
- created_at
- updated_at
```

主要索引：

- `creator_id + platform_content_id` 唯一索引。
- `published_at` 索引。
- `creator_id + published_at` 联合索引。

### 5.5 内容数据快照

```text
content_snapshots
- id
- content_id
- like_count
- comment_count
- collect_count
- share_count
- captured_at
```

主要索引：

- `content_id + captured_at` 联合索引。

### 5.6 评论

```text
comments
- id
- content_id
- platform_comment_id
- author_name
- author_platform_id
- comment_text
- like_count
- published_at
- first_discovered_at
- status
- created_at
- updated_at
```

### 5.7 预警与任务执行

```text
alert_rules
- id
- name
- alert_type
- conditions_json
- notification_channels_json
- is_enabled
- created_at
- updated_at

alerts
- id
- creator_id
- content_id
- rule_id
- alert_type
- severity
- title
- message
- status
- triggered_at
- read_at

collection_runs
- id
- creator_id
- task_type
- status
- started_at
- finished_at
- error_message
- result_summary_json
```

---

## 6. 平台采集适配器设计

采集逻辑必须通过统一接口访问，避免将平台细节写进业务代码。

```python
class CreatorCollector:
    def resolve_account(self, profile_url: str): ...

    def fetch_creator_profile(self, account_id: str): ...

    def fetch_recent_posts(self, account_id: str): ...

    def fetch_post_metrics(self, post_id: str): ...

    def fetch_post_comments(self, post_id: str): ...
```

建议实现以下适配器：

```text
MockCollector
用于开发、测试和演示，不访问真实平台。

ManualImportCollector
支持通过 CSV 或人工录入数据。

DouyinPublicCollector
获取合规可访问的抖音公开数据。

XiaohongshuPublicCollector
获取合规可访问的小红书公开数据。

AuthorizedCollector
后续对接官方授权接口。
```

每次采集执行的标准流程：

```text
读取账号配置
    ↓
调用对应平台适配器
    ↓
校验和标准化数据
    ↓
更新账号最新状态
    ↓
保存账号快照
    ↓
发现并保存新内容
    ↓
更新重点内容快照
    ↓
执行预警规则
    ↓
生成通知
    ↓
记录任务执行结果
```

---

## 7. API 初步设计

### 7.1 账号管理

```text
POST   /api/v1/creators
GET    /api/v1/creators
GET    /api/v1/creators/{creator_id}
PATCH  /api/v1/creators/{creator_id}
DELETE /api/v1/creators/{creator_id}
POST   /api/v1/creators/{creator_id}/collect
GET    /api/v1/creators/{creator_id}/snapshots
```

### 7.2 内容与评论

```text
GET /api/v1/posts
GET /api/v1/posts/{post_id}
GET /api/v1/posts/{post_id}/snapshots
GET /api/v1/posts/{post_id}/comments
```

### 7.3 预警与仪表盘

```text
GET   /api/v1/alerts
PATCH /api/v1/alerts/{alert_id}/read
GET   /api/v1/dashboard/summary
GET   /api/v1/dashboard/trends
GET   /api/v1/dashboard/rankings
```

### 7.4 系统配置

```text
GET   /api/v1/alert-rules
POST  /api/v1/alert-rules
PATCH /api/v1/alert-rules/{rule_id}
GET   /api/v1/collection-runs
```

---

## 8. 项目分阶段实施计划

### 阶段 0：需求确认与开发准备

建议周期：1 至 2 天。

### 工作内容

- 确认第一批需要监控的平台与账号数量。
- 确认监控频率和重点指标。
- 确认第一版通知渠道。
- 确认后端 Python、Node.js、Docker 等本地开发环境。
- 建立 Git 仓库和基础分支策略。

### 需要明确的问题

- 第一批预计监控多少个账号？
- 是否只供内部使用？
- 是否需要多用户登录？
- 第一版优先抖音还是小红书？
- 是否已经有可用的官方接口、第三方接口或数据导出渠道？

### 验收标准

- 第一版范围得到确认。
- 开发环境可以运行 Docker。
- 项目代码仓库可正常提交。

---

### 阶段 1：搭建项目骨架和基础环境

建议周期：2 至 3 天。

### 工作内容

1. 创建 Vue3 前端项目。
2. 创建 FastAPI 后端项目。
3. 创建 MySQL 与 Redis 的开发用 Docker Compose。
4. 配置 SQLAlchemy 和 Alembic。
5. 配置 Celery Worker 和 Celery Beat。
6. 建立统一日志、异常处理和配置管理。
7. 创建健康检查接口。

### 开发阶段运行方式

本地运行，方便调试：

```text
Vue3
FastAPI
Celery Worker
Celery Beat
```

Docker 运行：

```text
MySQL
Redis
```

### 验收标准

- MySQL 和 Redis 可以通过 Docker Compose 启动。
- FastAPI 可以连接 MySQL 与 Redis。
- Alembic 可以创建和更新数据库表。
- Celery Worker 可以收到并执行测试任务。
- Celery Beat 可以按周期发送测试任务。
- Vue3 可以调用 FastAPI 健康检查接口。

---

### 阶段 2：完成账号监控基础闭环

建议周期：4 至 6 天。

### 工作内容

1. 创建账号、账号快照、采集记录等核心数据表。
2. 完成账号管理 API。
3. 完成账号管理前端页面。
4. 实现 `MockCollector`。
5. 实现立即采集和定时采集任务。
6. 保存账号历史快照。
7. 展示账号基础趋势图。

### 为什么先使用 MockCollector

真实平台采集存在不确定性。先使用模拟数据，可以验证整个系统链路：

```text
添加账号
→ 定时任务执行
→ 数据发生变化
→ 保存快照
→ 前端展示趋势
```

### 验收标准

- 可以添加、编辑、暂停和删除监控账号。
- 可以设置账号采集频率。
- 可以手动触发一次采集。
- 定时任务能够自动采集模拟数据。
- 前端可以展示粉丝与获赞趋势。
- 采集失败会留下明确记录。

---

### 阶段 3：完成内容动态与预警闭环

建议周期：5 至 7 天。

### 工作内容

1. 创建内容、内容快照、预警规则和预警记录表。
2. 扩展 MockCollector，使其能够生成新内容。
3. 建设动态流页面。
4. 建设预警中心页面。
5. 实现新内容预警。
6. 实现数据增长阈值预警。
7. 接入一个通知渠道，建议优先飞书或企业微信机器人。

### 验收标准

- 系统能识别账号发布的新内容。
- 系统不会重复保存同一内容。
- 系统能够持续保存内容指标快照。
- 满足规则时能够生成预警。
- 通知渠道能够收到新内容提醒。

完成本阶段后，系统已经具备可演示、可验证的 MVP。

---

### 阶段 4：接入真实公开数据

建议周期：根据平台能力评估，通常至少 1 至 3 周。

### 工作内容

1. 先选择一个平台和一种稳定数据来源。
2. 实现账号链接解析与账号身份确认。
3. 实现真实账号公开数据采集。
4. 实现真实内容列表与指标采集。
5. 增加限流、重试、超时、代理与失败降级策略。
6. 增加采集结果质量检查。
7. 记录采集器版本与原始数据。

### 推荐实施顺序

```text
人工导入或第三方合规接口
→ 官方授权接口
→ 公开数据适配器
→ 另一平台适配器
```

### 验收标准

- 至少一个平台可以稳定获取指定账号的公开数据。
- 新内容发现延迟符合设定目标。
- 同一数据不会重复写入。
- 采集失败不会影响 API 服务。
- 连续失败能够触发系统预警。

---

### 阶段 5：评论监控与运营分析

建议周期：5 至 10 天。

### 工作内容

- 获取并保存公开评论。
- 识别新增评论。
- 添加关键词规则。
- 添加负面评论与高价值评论标记。
- 增加账号增长榜和内容互动榜。
- 增加日报和周报。

### 验收标准

- 可以查看各监控内容的新评论。
- 可以通过关键词筛选评论。
- 可以生成每日监控摘要。
- 可以查看账号和内容排行。

---

### 阶段 6：生产部署与规模化

建议周期：3 至 7 天。

### 工作内容

- 将 FastAPI、Celery Worker、Celery Beat、Vue3/Nginx 放入 Docker。
- 增加 HTTPS 与域名配置。
- 增加生产环境变量管理。
- 增加数据库自动备份。
- 增加日志采集、健康检查和服务重启策略。
- 增加采集任务并发控制。
- 制定历史快照归档策略。

### 验收标准

- 一条命令可启动完整服务。
- 服务重启后任务与数据不会丢失。
- MySQL 有可验证的备份和恢复方案。
- Worker 异常退出后可以自动恢复。
- 可以查看服务健康状态与采集失败情况。

---

## 9. 开发与构建流程

### 9.1 首次创建项目

建议按以下顺序进行：

```text
1. 创建项目目录与 Git 仓库
2. 创建 FastAPI 项目骨架
3. 创建 Vue3 项目骨架
4. 创建开发用 Docker Compose
5. 启动 MySQL 和 Redis
6. 配置数据库迁移
7. 配置 Celery
8. 验证前后端与任务链路
9. 开始开发业务功能
```

### 9.2 日常开发启动流程

```text
1. 启动 MySQL 和 Redis
2. 执行数据库迁移
3. 启动 FastAPI
4. 启动 Celery Worker
5. 启动 Celery Beat
6. 启动 Vue3
7. 开发并运行测试
```

预期命令将在项目骨架完成后固定为类似形式：

```powershell
docker compose -f docker-compose.dev.yml up -d

cd backend
alembic upgrade head
uvicorn app.main:app --reload

celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info

cd frontend
npm run dev
```

Windows 环境下 Celery Worker 可能存在兼容性问题。若本地运行不稳定，优先将 Worker 与 Beat 放入 Linux Docker 容器运行。

### 9.3 数据库变更流程

任何数据库结构调整都必须通过 Alembic 迁移完成：

```text
修改 SQLAlchemy 模型
→ 生成 Alembic 迁移
→ 检查迁移脚本
→ 本地执行迁移
→ 运行测试
→ 提交代码
```

不要直接在生产数据库手动修改表结构。

### 9.4 正式环境构建流程

```text
1. 拉取指定版本代码
2. 创建生产环境变量文件
3. 构建 Docker 镜像
4. 启动 MySQL、Redis、FastAPI、Worker、Beat、Nginx
5. 执行数据库迁移
6. 检查健康状态
7. 执行一次测试采集
8. 检查预警与通知
```

---

## 10. 测试策略

### 10.1 单元测试

- 预警规则计算。
- 数据标准化。
- 快照变化计算。
- 账号与内容去重。
- 采集任务重试策略。

### 10.2 集成测试

- FastAPI 与 MySQL。
- Celery 与 Redis。
- 定时任务到快照保存的完整链路。
- 新内容发现到预警生成的完整链路。

### 10.3 采集器契约测试

所有平台适配器必须返回统一的数据结构。真实采集器和 MockCollector 应通过相同测试。

### 10.4 上线前检查

- 是否存在重复账号或重复内容。
- 快照是否按照预期生成。
- 失败任务是否有日志。
- 重试是否会造成重复数据。
- 通知是否可能重复发送。
- 数据库备份是否能够恢复。

---

## 11. 运行维护与风险控制

### 11.1 采集频率建议

| 账号等级 | 建议采集频率 |
| --- | --- |
| 重点账号 | 15 至 30 分钟 |
| 普通账号 | 1 至 3 小时 |
| 低优先级账号 | 每天 1 至 2 次 |

第一版不要对所有账号进行高频采集。

### 11.2 数据量预估

若监控 1,000 个账号，每小时保存一次账号快照：

```text
1,000 × 24 × 365 = 8,760,000 条账号快照 / 年
```

MySQL 可以处理该规模，但需要：

- 建立正确索引。
- 避免无意义的高频快照。
- 数据没有变化时可选择不保存完整快照。
- 定期归档长期历史数据。
- 对趋势查询增加缓存或汇总表。

### 11.3 关键监控指标

- API 响应时间与错误率。
- Celery 队列积压数量。
- 任务成功率与平均执行时长。
- 单个平台连续采集失败数量。
- 每日新增账号、内容、评论和快照数量。
- 通知发送成功率。
- MySQL 与 Redis 健康状态。

### 11.4 主要风险

| 风险 | 应对方式 |
| --- | --- |
| 平台页面或接口发生变化 | 采集器独立封装并保留版本 |
| 平台限制访问频率 | 分级采集、限流、退避重试 |
| 无法获取后台数据 | 第一版只依赖公开数据 |
| 数据量持续增长 | 索引、汇总、归档与备份 |
| Celery 重复执行任务 | 使用幂等设计和唯一约束 |
| 通知重复发送 | 为预警生成唯一键 |
| 单个平台故障影响全部任务 | 按平台拆队列并做失败隔离 |

---

## 12. MVP 范围与完成定义

第一版 MVP 只包含：

- 管理员登录。
- 添加、编辑、暂停监控账号。
- 支持账号分组与监控频率配置。
- 定时检查账号公开数据。
- 保存账号数据快照。
- 发现并保存新内容。
- 展示账号列表、动态流和趋势图。
- 生成新内容和数据增长预警。
- 通过一个渠道发送提醒。
- 查看采集任务执行记录。

第一版暂不包含：

- 完整播放量、曝光量、完播率等后台数据。
- 复杂多租户与精细权限。
- 自动回复评论。
- AI 内容生成。
- 大规模实时数据仓库。
- 同时接入大量不稳定数据来源。

### MVP 完成定义

使用 MockCollector 或一个稳定真实数据来源时，系统能够：

```text
添加指定账号
→ 按配置周期执行监控
→ 保存账号与内容变化
→ 发现新内容
→ 生成预警
→ 通知运营人员
→ 在前端查看历史趋势
```

---

## 13. 建议里程碑

| 里程碑 | 交付结果 | 预计累计时间 |
| --- | --- | --- |
| M1 基础链路 | 前后端、MySQL、Redis、Celery 全部跑通 | 第 1 周 |
| M2 账号监控 | 账号管理、模拟采集、快照趋势 | 第 2 周 |
| M3 MVP 完成 | 新内容发现、预警、通知、动态流 | 第 3 周 |
| M4 真实数据 | 至少接入一个稳定数据来源 | 第 4 至 6 周 |
| M5 运营增强 | 评论监控、榜单、日报周报 | 第 6 周以后 |

具体周期会受到真实平台数据来源、账号规模和开发投入影响。

---

## 14. 当前最优执行顺序

从现在开始，建议严格按照以下顺序实施：

1. 创建 FastAPI、Vue3 项目骨架。
2. 创建只包含 MySQL 和 Redis 的开发用 Docker Compose。
3. 验证 FastAPI、MySQL、Redis、Celery、Vue3 的完整链路。
4. 创建核心数据表和 Alembic 迁移。
5. 实现账号管理和 MockCollector。
6. 实现账号数据快照和趋势图。
7. 实现内容发现、预警与通知。
8. 完成 MVP 验收。
9. 评估并接入一种真实、稳定、合规的数据来源。
10. 再扩展评论分析、榜单和后台授权数据。

这样可以确保即使真实平台采集暂时受限，系统主体仍然能够完成开发、测试和演示。
