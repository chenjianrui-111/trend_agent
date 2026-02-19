# TrendAgent

TrendAgent 是一个面向“热点抓取 -> 内容理解 -> 跨平台发稿 -> AIGC 视频”的多 Agent 自动化系统。

目标是把你选定的平台热点（文章/视频）快速转成可发布内容，并支持向国内平台分发，必要时自动生成配套视频素材。

## 核心能力

1. 热点抓取（文章/视频）
- 多源抓取：`twitter`、`youtube`、`weibo`、`bilibili`、`zhihu`
- 支持按来源选择抓取、按关键词抓取、按数量限制抓取
- 内置去重与热度排序，优先输出高互动内容

2. 内容类型识别与筛选
- LLM 分类：`AI/政治/娱乐/科技/财经/体育/健康/科学/生活/教育/其他`
- 支持 `categories_filter` 进行“只要某些类型”的筛选

3. 跨平台内容生成与发稿
- 按目标平台生成差异化稿件：`wechat`、`xiaohongshu`、`douyin`、`weibo`
- 支持发布器并发执行、失败重试、发布结果落库
- 可作为“国内平台自动发稿中枢”使用

4. AIGC 视频生成
- 支持视频服务商：`keling`、`runway`、`pika`
- 自动将文本草稿转为视频 prompt，轮询生成结果
- 支持失败后 provider fallback

5. 质量与合规
- 敏感词检测 + 长度约束 + 可选 LLM 质检
- 对每条草稿打分并标记 `quality_passed`

6. 过程与总体监控
- Prometheus 指标：抓取、分类、草稿生成、发布、视频、HTTP 请求
- Grafana 面板可直接接入

## 端到端流程

```text
抓取(scraping)
  -> 分类(categorizing)
  -> 平台化改写(summarizing)
  -> 质量检查(quality_checking)
  -> [可选] 视频生成(video_generating)
  -> 平台发布(publishing)
  -> 完成(completed)
```

调度方式：
- 手动触发（API）
- 定时触发（APScheduler + Cron）

## 项目结构

```text
trend_agent/
  api/             FastAPI 接口（auth/content/pipeline/publish/video/schedule）
  agents/          Scraper/Categorizer/Summarizer/Quality/Video/Publisher/Orchestrator
  scrapers/        各平台抓取器
  publishers/      各平台发布器
  video/           AIGC 视频 provider 客户端
  services/        content_store、dedup、llm_client、scheduler
  models/          消息模型、状态机、数据库模型
  observability/   Prometheus 指标
  web/             简易前端看板
```

## 快速启动

### 1) 本地运行

```bash
cd ../trend_agent
cp .env.example .env

pip install -r requirements.txt
python -m trend_agent.main
```

默认地址：`http://127.0.0.1:8090`

### 2) Docker Compose

```bash
cd ../trend_agent
cp .env.example .env
docker compose up -d --build
```

服务端口：
- API: `8090`
- Prometheus: `9090`
- Grafana: `3000`

## 关键环境变量

- 应用
  - `APP_ENV` (`development|production`)
  - `PORT` (默认 `8090`)

- 抓取
  - `SCRAPER_ENABLED_SOURCES=twitter,youtube,weibo,bilibili`
  - `TWITTER_BEARER_TOKEN`
  - `YOUTUBE_API_KEY`
  - `WEIBO_ACCESS_TOKEN`
  - `BILIBILI_SESSDATA`

- 发稿
  - `WECHAT_APP_ID` / `WECHAT_APP_SECRET`
  - `XIAOHONGSHU_COOKIE`
  - `DOUYIN_ACCESS_TOKEN`
  - `WEIBO_PUBLISH_TOKEN`

- 视频
  - `VIDEO_DEFAULT_PROVIDER=keling`
  - `KELING_ACCESS_KEY` / `KELING_SECRET_KEY`
  - `RUNWAY_API_KEY`
  - `PIKA_API_KEY`

- LLM
  - `LLM_PRIMARY_BACKEND`（默认 `zhipu`）
  - `ZHIPU_API_KEY` / `ZHIPU_MODEL`
  - `OPENAI_API_KEY` / `OPENAI_MODEL`
  - `OLLAMA_BASE_URL` / `OLLAMA_MODEL`

## API 概览

认证：
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

内容与素材：
- `GET /api/v1/content`
- `GET /api/v1/content/{draft_id}`
- `PUT /api/v1/content/{draft_id}`
- `DELETE /api/v1/content/{draft_id}`
- `GET /api/v1/sources`

Pipeline：
- `POST /api/v1/pipeline/run`（完整流程触发）
- `GET /api/v1/pipeline/runs`
- `GET /api/v1/pipeline/runs/{run_id}`

发布/视频/调度：
- `POST /api/v1/publish`
- `GET /api/v1/publish/history`
- `POST /api/v1/video/generate`
- `GET /api/v1/schedules`
- `POST /api/v1/schedules`
- `DELETE /api/v1/schedules/{schedule_id}`

系统：
- `GET /api/v1/health`
- `GET /metrics`

## 手动触发示例

```bash
curl -X POST http://127.0.0.1:8090/api/v1/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{
    "sources": ["weibo", "bilibili"],
    "categories_filter": ["AI", "科技"],
    "target_platforms": ["wechat", "xiaohongshu", "douyin"],
    "generate_video": true,
    "video_provider": "keling",
    "max_items": 30
  }'
```

## 当前实现说明

- Pipeline 主链路（抓取/分类/改写/质检/发布/可选视频）已经串通。
- `publish`、`video`、`schedule` 的部分 API 仍属于“触发入口”风格，建议在业务侧配合 pipeline run id 做异步追踪。
- 生产落地建议：
  - 使用独立数据库（PostgreSQL）
  - 对接真实平台凭证管理（密钥服务）
  - 将 3000/9090 仅开放内网或通过网关鉴权

