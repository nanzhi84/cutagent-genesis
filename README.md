# CutFlow

面向本地商家与服务商的 **Case-first 数字人短视频交付平台**。

它解决的不是「偶尔生成一条看起来不错的视频」，而是更难的经营问题：怎样围绕同一个账号，持续、稳定、可核算地生产内容，并让每轮结果回流到下一轮。

<img
  src="docs/assets/cutflow-flow.svg"
  alt="CutFlow 以 Case 为长期边界，由 Temporal 将任务路由到规则数字人主链、Agent 智能剪辑链或 Seedance 信息流生成支链，三条链共享供应商、数据、媒体、运营与发布治理底座"
  width="100%"
/>
<br>
<sub>CutFlow 三链路系统架构 · 规则剪辑、Agent 剪辑、Seedance 原生生成与发布数据回流</sub>

---

## Case-first：让系统记住一个账号，而不是只记住一次任务

传统 AI 视频工具通常从一段 prompt 开始，生成结束后上下文也随之消失。CutFlow 把 **Case** 作为长期产品边界：

- 账号定位、品牌禁区、目标受众和内容策略进入 Case 上下文
- 脚本、素材、音色、Prompt 版本和供应商配置都绑定到明确的生产事实
- 每次成片、发布与效果数据回流到评分卡和复盘流程
- 下一轮创作读取的是被验证过的账号经验，而不是重新从空白 prompt 猜测

因此，CutFlow 更像一个内容操作系统，而不是一次性生成器。

---

## 三条视频生产流水线

创建视频时，用户面对的不是三个只在节点数量上不同的技术模板，而是三种不同的生产方式：**用规则剪已有素材、让 Agent 在已有素材中做选择，或者让视频模型直接生成整条广告。**

| 链路 | 画面从哪里来 | 谁做核心决策 | 更适合什么任务 |
| --- | --- | --- | --- |
| 规则剪辑主链 | Case 素材库中的数字人和 B-roll | 检索结果与固定规则 | 稳定、批量、可复现的日常内容生产 |
| Agent 智能剪辑链 | 同一套 Case 素材库 | 媒体选择 Agent + 独立 BGM Agent | 需要理解脚本语义和具体剪辑要求的内容 |
| Seedance 信息流支链 | 视频模型原生生成，可附参考图片或视频 | Seedance 生成模型 | 快速制作 15 秒原生信息流广告 |

无论选择哪一条链，系统都会创建独立的 `WorkflowRun`，记录节点状态、供应商调用、成本和最终产物。三条链共用 Case、ProviderGateway、对象存储、导出和运行报告，但只执行自己真正需要的生产步骤。

### 1. 用规则稳定出片：数字人主链

`digital_human_v2` 是 CutFlow 的基础生产链，共 **19 个节点**。它解决的是一个很实际的问题：商家已经有数字人口播素材、门店和产品 B-roll、音色、字体与配乐，系统怎样把这些资产持续组合成结构稳定、可以批量交付的视频。

一条任务进入后，链路会依次完成：

1. **确认生产条件：** 校验脚本、音色、字幕、B-roll 和口型配置，并加载当前 Case 的品牌信息、素材和历史使用记录
2. **把脚本变成可剪辑的时间轴：** 生成旁白，对齐每句话的真实起止时间，再根据语句边界编译出可以安全切镜的数字人窗口和 B-roll 窗口
3. **为每个窗口找素材：** 根据当句话的内容、素材标注和检索结果建立候选集，同时排除时长不够、时间冲突或近期使用过多的素材
4. **按照规则完成指派：** 在每个窗口的合法候选中，综合匹配分、可用时长、素材唯一性和重复使用惩罚选择数字人或 B-roll；不让模型临时改时间点，也不允许同一素材无约束地反复出现
5. **合成数字人和画面：** 生成数字人轨道并完成 LipSync，把数字人和 B-roll 装入已经校验过的帧级时间线，再交给 FFmpeg 渲染
6. **完成包装与交付：** 按固定规则生成字幕带，根据脚本匹配可用 BGM 片段，完成混音和文件质检，最后输出成片、封面、发布文案、发布包与运行报告

这里的“确定性”并不是说整条链完全不用模型。创意意图和检索 query 仍然可以由模型辅助生成，但最终用哪个素材、放在哪个合法窗口、字幕怎样排、视频怎样渲染，都要经过明确规则和数据契约。

主链还支持两种画面模式：`insert` 保留数字人口播为主画面，只在重点语句插入 B-roll；`full_coverage` 则让 B-roll 覆盖整段旁白，并直接跳过数字人轨道和 LipSync。后者是同一条生产链中的「纯 B-roll 画外音」模式，不需要再维护第四套模板。

### 2. 让模型理解剪辑要求：Agent 智能剪辑链

`digital_human_editing_agent_v2` 共 **20 个节点**。它并不是让 Agent 从零生成视频，也不是把整条时间线交给大模型自由发挥；它与主链使用相同的脚本、配音、旁白时间戳、素材库、时间窗口、LipSync、字幕、渲染和导出能力，只替换了其中最需要语义判断的两个环节。

**画面选择：** 用户可以额外输入「尽量使用穿搭相近的人像」「讲到施工时多展示细节」等剪辑要求。媒体选择 Agent 会同时看到脚本、逐句时间、已经编译好的镜头窗口，以及每个窗口允许使用的人像和 B-roll 候选。Agent 只回答「这个窗口选哪个候选、为什么」，不能新增素材、创造不存在的时间点，也不能修改字幕或配乐。输出后系统还会逐项校验：窗口是否全覆盖、素材是否足够、选择是否来自合法候选、是否重叠或重复使用；不符合约束的结果必须先修复或停止生产。

**配乐选择：** 独立的 BGM Agent 只从已经完成标注、能够真实裁切的音乐片段中选择一个 `bgm_id`；它不能碰画面，也不能决定字幕。固定字幕带先由确定性节点生成，再与选中的 BGM 混入成片。把媒体、BGM 和字幕拆开，是为了避免一个「大而全」的 Agent 同时修改太多生产事实。

### 3. 直接生成整条广告：Seedance 信息流支链

`seedance_t2v_v1` 是一条独立的 **5 节点短链**。它服务的不是「用库存素材剪一条数字人视频」，而是快速生成一条原生信息流广告。当前规格固定为 **15 秒、3:4、720p**，既可以只输入口播脚本，也可以从 Case 的 AI 素材中附带人物、门头、产品或环境图片 / 视频作为参考。

系统会把脚本组织成「人物出镜口播 + 中段 B-roll 穿插 + 结尾回到人物」的信息流结构，并要求 Seedance 同时生成画面、自然口播和口型。因为声音与画面已经由视频模型一次生成，这条链不会再执行数字人主链中的 TTS、ASR、素材检索、LipSync、时间线装配、本地字幕和 BGM 混音。

生成完成后，平台直接把视频登记为成片，从视频中抽取一帧作为封面，并生成发布包和运行报告。供应商生成失败时不会自动重试，避免重复扣费后又得到一条内容不同的视频。

三条链最终形成分层关系：**规则主链负责稳定交付，Agent 链负责在稳定框架里增加语义判断，Seedance 支链负责原生生成和快速试错。**

---

## 多模型能力如何被产品化

流水线需要 LLM、VLM、TTS、ASR、对口型、文生图和文生视频等多种外部能力。CutFlow 没有把这些 SDK 分散写进业务节点，而是通过 `ProviderGateway` 按能力路由：

- 节点只声明需要哪种能力，不直接绑定某一家模型
- Provider Profile、Secret Store 和 Prompt Registry 分别管理供应商、密钥与提示词版本
- 未配置真实 provider 时显式失败；只有本地 demo 或测试可以明确打开 sandbox fallback
- 每次调用记录 token、耗时、预估 / 实际成本、模型与 Prompt 版本，便于追责和替换
- 幂等键与 typed artifact 让重试能够复用已经完成的外部调用和媒体产物

这套抽象的目的不是追求「接更多模型」，而是让供应商替换、价格变化和单点故障不再直接污染业务流程。

---

## 为重复交付设计的运营能力

CutFlow 把成本和成品率当作一等产品对象，而不是上线后再补日志：

- 11 项单片成本指标：成片、质检通过、发布、重试、浪费，以及按 provider / model / prompt 归因
- 11 项成品率漏斗：从任务进入、各阶段完成，到质检、人工确认和发布
- 预算阈值、余额监控、熔断和告警在调用前后参与决策
- 内容哈希、节点输入和 artifact manifest 共同决定哪些结果可以安全复用
- 素材 ledger 会降低近期反复使用素材的权重，减少连续视频里的画面重复
- 降级、返工和人工审批都写入审计事件，不允许静默吞掉失败

---

## 工程架构

- **FastAPI + OpenAPI** 是 API 与 React 控制台的契约事实源
- **Temporal** 承载长流程、重试、取消、恢复和多 worker 编排；API 只负责准入与控制
- **PostgreSQL / SQLAlchemy** 保存业务事实，**对象存储**保存媒体与中间产物
- **Redis** 只用于多副本下的限流、实时事件 fanout 和协调，不被当作业务真源
- **FFmpeg / FFprobe** 负责转码、裁切、对齐、时间线渲染、字幕与 BGM 混合及输出验证
- **ProviderGateway + Prompt Registry** 管理多模型调用和提示词生命周期
- **OceanEngine / XLSX connector** 将外部效果数据带回复盘链路

```text
apps/
  api/          FastAPI：路由、鉴权、准入与控制面
  worker/       Temporal worker：消费生产任务队列（独立进程）
  web/          React / Vite 控制台（类型来自 OpenAPI）
  connectors/   离线 ETL（OceanEngine / XLSX）
packages/
  core/         契约、配置、存储、鉴权、观测、工作流、对象存储、Secret
  ai/           ProviderGateway、Prompt Registry、真实 provider 插件
  creative/     Case、脚本、自进化、评分卡
  media/        素材、标注、音频、视频、封面、渲染辅助
  planning/     素材匹配、确定性选择、剪辑规划
  production/   流水线节点、成片仓储、剪映 / 编辑器交接
  publishing/   发布仓储、文案 / 封面、平台 adapter
  ops/          成本、成品率、预算、告警、余额与熔断
```

数据库迁移只在 `packages/core/storage/alembic/versions/`。更细的长期设计见 [docs/README.md](docs/README.md)。

---

## 本地启动

### 前置依赖

- Python 3.12+
- Node.js 22
- Docker + Docker Compose v2
- `ffmpeg` / `ffprobe` 在 `PATH` 上，或用 `CUTAGENT_FFMPEG_BIN` / `CUTAGENT_FFPROBE_BIN` 指定

### 推荐：一键启动

```bash
cp .env.example .env.local
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
( cd apps/web && npm install )

scripts/dev_up.sh up
scripts/dev_up.sh status
```

常用日志与停止：

```bash
scripts/dev_up.sh logs api
scripts/dev_up.sh logs worker
scripts/dev_up.sh logs web
scripts/dev_up.sh down            # 停应用进程
scripts/dev_up.sh down --infra    # 连本地 infra 一起停
```

### 手动启动

先拉起基础设施：

```bash
docker compose up -d postgres redis minio temporal temporal-ui
python scripts/bootstrap_database.py
# 字幕 v2 需要确定性 CJK 字体包（首次）
python scripts/import_font_assets.py
```

再分别启动：

```bash
python -m uvicorn apps.api.main:app --reload --port 8000
python -m apps.worker
( cd apps/web && npm run dev )
```

### 常用端口与本地账号

| 服务 | 地址 |
| --- | --- |
| API | `http://localhost:8000` |
| Web | `http://localhost:8001`（`dev_up`）或 Vite `5173` |
| Postgres | `localhost:55432` |
| Redis | `6379` |
| MinIO | `9000` / `9001` |
| Temporal | `7233` · UI `8080` |

本地种子账号：

- `admin@local.cutagent` / `local-admin`
- `viewer@local.cutagent` / `local-viewer`

### 关键配置提示

默认存储后端是 SQLAlchemy，启动前需要数据库连接（完整清单见 [.env.example](.env.example)）：

```bash
export CUTAGENT_STORAGE_BACKEND=sqlalchemy
export CUTAGENT_DATABASE_URL=postgresql+psycopg://cutagent:cutagent@localhost:55432/cutagent
export CUTAGENT_WORKFLOW_RUNTIME=temporal
export CUTAGENT_TEMPORAL_ADDRESS=localhost:7233
export CUTAGENT_TEMPORAL_TASK_QUEUE=cutagent-production
```

Temporal 模式下，durable / ephemeral 对象存储必须是共享 MinIO 或 S3，不能是某个节点本地目录。真实 provider 未配置时默认显式失败；本地 demo 可设 `CUTAGENT_ALLOW_SANDBOX_FALLBACK=1`。

`CUTAGENT_REDIS_URL` 是可选的跨进程协调层（限流、事件 fanout、stream token），不是查询缓存，也不是业务真源。多副本生产会强制要求 Redis。详见 [docs/architecture/redis-coordination.md](docs/architecture/redis-coordination.md)。

---

## 开发与验证

改 API 形状后必须重生成契约产物（`schema.d.ts` 禁止手改）：

```bash
uv run --extra dev python scripts/export_openapi.py
( cd apps/web && npm run generate:api )
```

常用验证：

```bash
python -m pytest -q                  # 默认套件（含 SQL 集成；需 Postgres）
( cd apps/web && npm run build )
scripts/ci_gate.sh                   # 完整本地门禁
```

Temporal 测试需真实 Temporal + 共享 MinIO/S3：

```bash
export CUTAGENT_RUN_TEMPORAL_TESTS=1
python -m pytest -q tests/temporal
```

改 `packages/production` 或节点代码后，记得**重启 worker**，不只是 API。

---

## 文档

长期文档入口：[docs/README.md](docs/README.md)

- [Milestones](docs/milestones.md)
- [关键技术选型](docs/technical-choices.md)
- [关键设计决策](docs/design-decisions.md)
- [Redis 跨进程协调层](docs/architecture/redis-coordination.md)
- [可恢复上传与原子登记](docs/architecture/resumable-upload.md)
- [工作流取消与产物提交栅栏](docs/architecture/workflow-cancellation.md)
