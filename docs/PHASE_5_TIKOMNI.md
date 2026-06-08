# 阶段 5：TikOmni 真实内容数据源接入

## 目标

本阶段新增 `tikomni_douyin` 采集器，用 TikOmni API 替代不稳定的抖音公开主页渲染链路，让“内容动态”页可以展示真实作品和真实互动指标。

第一版只接入抖音，不接小红书；只采集作品互动数量，不抓评论正文。

## 配置项

`.env` 需要增加：

```env
TIKOMNI_ENABLED=true
TIKOMNI_API_BASE_URL=https://api.tikomni.com
TIKOMNI_API_TOKEN=
TIKOMNI_TIMEOUT_SECONDS=60
TIKOMNI_DAILY_BUDGET_CNY=20
TIKOMNI_ESTIMATED_UNIT_PRICE_CNY=0.008
```

注意：`TIKOMNI_API_TOKEN` 只写在本地 `.env`，不要提交到 Git。

## 采集器类型

系统目前支持：

```text
mock
douyin_public_web
tikomni_douyin
```

`tikomni_douyin` 只允许绑定抖音账号，小红书仍使用后续阶段单独接入。

## TikOmni 接口顺序

```text
/api/u1/v1/douyin/web/get_sec_user_id
/api/u1/v1/douyin/web/handler_user_profile
/api/u1/v1/douyin/app/v3/fetch_user_post_videos
/api/u1/v1/douyin/app/v3/fetch_multi_video
/api/u1/v1/douyin/app/v3/fetch_multi_video_statistics
```

## 字段范围

账号侧：

```text
昵称
头像
简介
地区
粉丝数
关注数
累计获赞
作品数
```

作品侧：

```text
作品 ID
标题/文案
发布时间
封面
作品链接
点赞数
评论数
收藏数
分享数
```

## 落库策略

第一版不新增业务表，继续复用：

```text
creator_accounts
creator_snapshots
content_posts
content_snapshots
collection_runs
```

同步规则：

```text
creator_id + platform_content_id 唯一
已存在作品只更新最新指标
每次成功或部分成功的指标采集都会生成 content_snapshots
TikOmni 请求数、估算成本和 endpoint 明细写入 collection_runs.result_summary
```

## 预算保护

每次 TikOmni 请求前检查当天估算成本：

```text
当天已估算成本 + 本次 run 已估算成本 + 单次接口估价 > TIKOMNI_DAILY_BUDGET_CNY
```

超过预算时：

```text
停止继续调用 TikOmni
不回退 mock
当前 run 标记 partial
content_status 标记 budget_limited
collection_runs.result_summary 记录 tikomni_budget_limited=true
```

## 前端变化

添加账号弹窗新增：

```text
TikOmni 真实 API
```

内容动态和账号详情需要区分：

```text
TikOmni
真实完整
真实部分可用
预算限制
采集失败
```

## 试采集脚本

新增只读脚本：

```bash
python scripts/probe_tikomni_douyin.py --profile-url "https://www.douyin.com/user/..."
```

用途：

```text
抖音主页链接 -> sec_user_id
sec_user_id -> 账号信息
sec_user_id -> 作品列表
aweme_id -> 作品详情/统计
输出字段映射报告
```

这个脚本不写数据库，只用于确认 TikOmni 返回字段是否符合当前映射。

## 验收场景

```text
1. 在 .env 填入 TIKOMNI_API_TOKEN
2. 添加一个抖音账号，数据来源选择 TikOmni 真实 API
3. 手动执行一次采集
4. 账号详情页出现真实账号指标
5. 内容动态页出现真实作品
6. 作品至少稳定展示点赞、评论、收藏、分享中可取得字段
7. 采集运行记录能看到 TikOmni 请求数和估算成本
8. 将预算调低后，采集停止继续调用并显示预算限制
```

## 后续阶段

阶段 5 跑通后再做：

```text
小红书 TikOmni 接入
评论列表与回复监控
按账号分级采集频率
成本日报与预算告警
```
