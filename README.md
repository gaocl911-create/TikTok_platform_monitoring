# Creator Monitoring

抖音 / 小红书指定创作者账号公开数据监测系统。

## 技术栈

- 前端：Vue3 + TypeScript + Vite
- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：MySQL 8
- 缓存与任务队列：Redis
- 异步任务：Celery + Celery Beat

## 开发环境启动

复制环境变量文件：

```powershell
Copy-Item .env.example .env
```

启动 MySQL 和 Redis：

```powershell
docker compose -f docker-compose.dev.yml up -d
```

开发环境中的 MySQL 默认使用宿主机端口 `13306`，Redis 使用 `16379`，避免与本机已有服务冲突。

启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8001
```

首次启动或模型发生变化后，执行数据库迁移：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

启动 Celery Worker：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app:celery_app worker --loglevel=info --pool=solo
```

启动 Celery Beat：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app:celery_app beat --loglevel=info
```

启动前端：

```powershell
cd frontend
npm install
npm run dev -- --port 5174
```

## 基础验证

- FastAPI 文档：`http://localhost:8001/docs`
- FastAPI 健康检查：`http://localhost:8001/health`
- Vue3 开发服务：`http://localhost:5174`

## 已实现功能

- 添加、编辑、暂停、恢复和删除监控账号
- 按平台、状态、昵称、账号 ID 和分组筛选账号
- MockCollector 模拟公开账号数据采集
- 添加账号时自动生成首次数据快照
- 支持手动立即采集
- Celery Beat 每分钟扫描到期账号并自动采集
- 展示账号粉丝、获赞、作品数与历史趋势
- 自动发现创作者的新内容并避免重复保存
- 每次采集持续保存内容点赞、评论、收藏和分享快照
- 内容动态流与内容快照详情
- 新内容预警与内容点赞增长阈值预警
- 预警规则启停、阈值配置和已读处理
- 支持飞书、企业微信和通用 JSON Webhook 通知
- 支持为账号选择模拟数据或抖音真实公开主页数据
- 真实采集失败不会回退到模拟数据，列表和详情页会展示数据来源与质量状态
- 账号快照和内容动态均记录数据来源，避免真实数据与模拟数据混淆

## Webhook 通知

在项目根目录 `.env` 中配置机器人 Webhook：

```dotenv
ALERT_WEBHOOK_URL=https://example.com/your-webhook
ALERT_WEBHOOK_TIMEOUT_SECONDS=5
```

配置后重启 FastAPI 和 Celery Worker。系统会根据 URL 自动适配飞书、企业微信或通用
JSON Webhook。未配置地址时，预警仍会正常生成，通知状态显示为 `skipped`。

当前已接入 `MockCollector` 和抖音真实公开主页采集器 `douyin_public_web`。抖音真实采集当前支持账号公开指标；
作品明细仍受公开页面可用性限制，小红书真实数据尚未接入。阶段四说明见
[docs/PHASE_4.md](./docs/PHASE_4.md)。

完整项目规划见 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。
