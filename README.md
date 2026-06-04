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

## 阶段二功能

- 添加、编辑、暂停、恢复和删除监控账号
- 按平台、状态、昵称、账号 ID 和分组筛选账号
- MockCollector 模拟公开账号数据采集
- 添加账号时自动生成首次数据快照
- 支持手动立即采集
- Celery Beat 每分钟扫描到期账号并自动采集
- 展示账号粉丝、获赞、作品数与历史趋势

当前采集器为 MockCollector，用于验证完整监控链路。真实抖音和小红书公开数据采集将在后续阶段接入。

完整项目规划见 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。
