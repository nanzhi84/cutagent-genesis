# 树影 Cutagent · Provider 用量/余额/花销监控 — 现状评估 + 落地方案

> 2026-06-22 多智能体审计（16 agent / 联网核实上游 API / 对抗式审查 / 主作者独立复核 9 条承重结论全部属实）。

## 0. 现状评估

**成熟度：4/10 — 架构骨架(端口+插件、逐次 ledger、快照表、手动刷新按钮、优雅降级)都搭好了，工程纪律可圈可点；但用户要的『实时看每个平台余额+花销』在真实部署里只对 runninghub.heygem 一家成立，余额默认完全不自动刷新、dashscope/openai/minimax 主成本大头查不到、余额与花销不对齐、无阈值告警、广告平台缺位，离可用还差核心几块拼图。**

总体上：系统的『花销侧』已经做得相当扎实，而『余额侧 + 实时性 + UI 一览』是真正的短板。花销侧——每次 provider 调用 gateway.invoke 无条件落一条 ProviderInvocation + UsageMeterRecord，匹配 ProviderPriceItem 算 estimated_cost，无价目不阻断而记 cost.unpriced 告警，逐次台账齐全且请求时实时 SQL GROUP BY 聚合(cost-rollups/dashboard)，这部分实时性是好的。余额侧是一套独立的端口+插件架构(packages/ops/balance)，6 个 poller 永不抛异常、失败优雅降级成 unconfigured/unsupported/unauthorized/error 状态字段，工程纪律很好。但问题是：8 个会计费的 provider 里，真正能查到余额的只有 runninghub.heygem 一个——dashscope 系 5 个全靠 AliyunBss 但 SDK 未装进 venv 恒 unsupported(且 BSS 只给账户级总额、无法按能力拆)，minimax 结构性无 API 恒 unsupported，openai.image 走真 OpenAI 会 error。其次实时性是『伪实时』：GET /api/providers/balances 只读 provider_balance_snapshots 快照，后台 BalancePollerService 默认关闭(且仅 API 进程内 asyncio loop、非 Temporal/cron，最快 15 分钟一拍)，不点『立即刷新』就看不到最新值。再次余额和花销是两套割裂数据，唯一交叉点是 reconcile 把余额快照首尾差当 actual 兜底，既不实时也不回写 invocation，cost_variance 恒 None。actual_cost 列全仓无代码写回，所以界面上看不到『真实花了多少钱』，只有估算值。UI 层面余额藏在『数据统计/analytics』页的一个 tab 里、需 admin 角色，不是首屏大盘，也没有 websocket/SSE 真推送，前端只是 60s 轮询快照。lipsync 两家(heygem/videoretalk)无 seed 价目，成片最贵环节按 0 元计，平台级花销被严重低估。OpsAlertRule 这套可配置阈值告警有库表+CRUD 但无评估引擎(连 alert_rules.py 都不存在)，余额也没有任何『低于阈值就提醒』的逻辑，ProviderBalanceItem 连阈值字段都没有。广告投放(巨量)的账户余额/消耗完全在监控范围外——connector 是纯离线 ETL，spec 也明确把余额界定为『Provider 余额/配额』不含投放账户。单位口径还不统一(coins/USD/CNY 混用，无归一)。一句话：花销估算的管道建好了，但『实时看每个平台真实余额』这件用户最关心的事，受限于上游 API 缺失/凭据不匹配/SDK 未装/默认不刷新，目前基本只对一个平台成立。

### 0.1 平台 × 监控能力 覆盖矩阵

| 平台 / provider | 计费 | 余额适配器 | 上游余额API | 逐次花销记录 | UI可见 | 刷新机制 | 状态 |
|---|---|---|---|---|---|---|---|
| MiniMax (api.minimaxi.com) — TTS | yes | packages/ops/balance/providers/minimax.py | no | yes — 插件硬编码 0.15 CNY/1k 字符，gateway 落 Usa… | yes 但恒 unsupported — Analytics… | on-demand(手动 refresh) / scheduled(poller 默认关 900s) | 🟡partial |
| 阿里云 DashScope/百炼 (dashscope.aliyuncs.com) — ASR/VLM/LLM/Omni/VideoReTalk | yes | packages/ops/balance/providers/aliyun_bss.py | yes | yes(token/秒 按 seed 价目) — 但 VideoReTalk 无… | yes 但实际查不到 — SDK 未装→恒 unsuppor… | on-demand / scheduled(默认关) | 🔴missing |
| RunningHub HeyGem (runninghub.ai) — lipsync 主路径 | yes | packages/ops/balance/providers/heygem.py | yes | partial — 报 provider_credits(consumeCoin… | yes — 8 家里唯一能真查到余额/配额的平台 | on-demand / scheduled(默认关) | 🟡partial |
| OpenAI 兼容图像 / neuromash 镜像 (实配 neuromashv1.cn) — image.generate | yes | packages/ops/balance/providers/openai_relay.py | yes | yes — 插件硬编码 0.4 CNY/张，报 provider_credits… | yes 但易 error — OpenAIRelay 为 n… | on-demand / scheduled(默认关) | 🟡partial |
| DeepSeek (api.deepseek.com) | no | packages/ops/balance/providers/deepseek.py | yes | n/a — 无调用插件，不产生 UsageMeter | no(默认) — seed 无对应 profile，除非运营… | on-demand / scheduled(默认关) | 🔴missing |
| Kimi/Moonshot (api.moonshot.cn) | no | packages/ops/balance/providers/kimi.py | yes | n/a — 无调用插件 | no(默认) — seed 无对应 profile | on-demand / scheduled(默认关) | 🔴missing |
| 巨量引擎 / OceanEngine (ad.oceanengine.com) — 广告投放 | yes | 无 — balance 子系统无 OceanEngine poller | yes | no — connector 只取『消耗』喂案例效果归因(performance… | no — 余额一览无投放平台维度，运营看不到『今天投放花了多… | manual(RPA 人工导出 XLSX) — 无任何主动拉取 | 🔴missing |

> 备注逐平台见各行 notes（完整版见原始审计结果）。

### 0.2 关键缺口（按严重度）

**🟥BLOCKER — 8 个计费 provider 里只有 runninghub.heygem 一个能查到真余额；主成本大头(LLM/ASR/VLM/TTS/图像)全查不到——dashscope 系全靠 AliyunBss 但 SDK 未装进 venv 恒 unsupported，且 BSS 只给账户级总额无法按能力拆；minimax 无 API；openai.image 命中真 OpenAI 路径返 HTML→error**

- 证据：`packages/ops/balance/providers/aliyun_bss.py:40-49; packages/ops/balance/providers/minimax.py:16-28; packages/ops/balance/providers/openai_relay.py:8-9,65-66; packages/ops/balance/registry.py:29-38`
- 影响：用户『实时看每个平台余额』的核心诉求基本落空：占花销绝大头的阿里云/图像/语音三类平台拿不到任何真实余额数字，余额面板对它们恒为 unsupported/error，无法及时管理充值。

**🟥BLOCKER — 余额非真正实时：GET balances 只读快照，后台 poller 默认关闭(CUTAGENT_BALANCE_POLLER_ENABLED=0)且为 API 进程内 asyncio loop(非 Temporal/cron)，最快 15 分钟一拍；不点『立即刷新』就看到任意旧值甚至 pending 空值**

- 证据：`apps/api/routers/providers.py:108-115; packages/ops/balance/service.py:55,84,116; packages/core/config/settings.py:378-382; apps/api/app.py:100-108`
- 影响：即便上游有余额 API，默认配置下也没有任何东西主动刷新，所谓『实时』退化为『上次有人手动点刷新时的旧快照』；要可靠定时还需额外引入 Temporal Schedule 或外部 cron，多副本下还会各自 fan-out 无去重。

**🟧HIGH — 余额与花销是两套割裂数据，无法在同一视图按平台对齐核对『账上还剩多少 / 这次跑掉多少真钱』；actual_cost 全仓无代码写回、cost_variance 恒 None，花销几乎全是 estimated 估算；reconcile 用余额快照首尾差当兜底，既不实时也不回写**

- 证据：`packages/ai/gateway/provider_gateway.py:322; packages/ops/sqlalchemy_repository.py:207,995,1062; packages/production/sqlalchemy_repository.py:1823`
- 影响：界面上看不到『实际花了多少钱』，只有下单时的预估；余额(平台真实)与花销(系统估算)对不上，无法回答用户最直接的问题，也无法精确对账。

**🟧HIGH — lipsync 两家(runninghub.heygem / dashscope.videoretalk)无 seed 价目，成功调用落 unpriced、估算 0 元，成片最贵环节按 0 计；HeyGem 的 coins 也无 coins→CNY 汇率，折不成钱**

- 证据：`packages/core/storage/provider_seed.py:115,228; packages/ai/providers/videoretalk.py:108; packages/ai/gateway/provider_gateway.py:295; packages/ai/providers/runninghub.py:107`
- 影响：平台级花销被系统性低估——口型同步是成片最贵环节却按 0 元入账，预算/告警/成本看板都偏低，误导成本管理决策。

**🟧HIGH — 广告投放平台(巨量/OceanEngine)的账户余额与消耗完全在监控范围外：connector 是纯离线 RPA XLSX 导入、不调线上 API、无密钥，消耗只进案例效果归因不汇入成本中心；balance 子系统无 OceanEngine poller**

- 证据：`apps/connectors/oceanengine/cli.py:8; apps/connectors/oceanengine/ingest.py:121; packages/ops/balance/registry.py:29; docs/树影_Cutagent_CleanSlate重写Spec_v3_2026-06-11.md:1556`
- 影响：若用户『每个远程接入平台』包含投放账户(巨量确有 fund/get 余额 API + report 消耗 API)，则完全缺失：看不到投放账户余额、看不到『今天投放花了多少』的跨平台聚合，需新接 OceanEngine 开放平台。

**🟨MED — 没有任何『余额低于阈值就提醒』能力：余额只拉取+展示+落快照，ProviderBalanceItem 连阈值字段都没有，无 low_balance 告警码；通用 OpsAlertRule 有库表+CRUD 但无评估引擎(连 alert_rules.py 文件都不存在)**

- 证据：`packages/core/contracts/providers.py:191-199; packages/ops/balance/service.py:31-128; packages/core/storage/alembic/versions/0008_ops_governance.py:60-74; packages/ops/sqlalchemy_repository.py:592-625`
- 影响：『及时管理』需要主动预警，但当前只能被动看面板；余额跌破水位不会通知人，运营只能靠人盯，容易因欠费导致生产链路中断。

**🟨MED — 余额一览没有专门的实时大盘：藏在 /analytics 页的一个 tab、需 admin 角色、refresh 需 operator，普通 viewer 看不到；前端仅 60s 轮询快照，无 websocket/SSE 推送；DeepSeek/Kimi 有适配器但 seed 无 profile，不会出现在面板**

- 证据：`apps/web/src/pages/AnalyticsPage.tsx:55; apps/web/src/components/analytics/BalanceQuotaTab.tsx:55; apps/web/src/App.tsx:43-45; packages/ai/providers/__init__.py:24`
- 影响：不是首屏一眼可见的实时大盘，权限分层让一线运营拿不到余额；DeepSeek/Kimi 是『有适配器无 provider』的空壳，进一步削弱『每个平台一览』的完整性。

**⬜LOW — 跨平台余额单位口径不一(HeyGem=coins、OpenAI 中转=USD、DeepSeek/Kimi/阿里云=CNY)，ProviderBalanceItem 不做单位归一/汇率换算**

- 证据：`packages/ops/balance/providers/heygem.py:14-39; packages/ops/balance/providers/openai_relay.py:27-66; packages/core/contracts/providers.py:191-220`
- 影响：无法『一眼看总余额』，跨平台对比需人工换算金币/美元/人民币，余额大盘可读性差。

---
# 树影 Cutagent · 平台余额 & 花销准实时观测落地方案（精修版）

## 1. 一句话结论

现状是「花销估算管道已搭好、但 heygem 这一最贵环节的花销因成本链未接 `provider_credits` 而恒为 0；余额侧只有 heygem 真正返了真值（CNY），其余平台要么只有账户级 API、要么完全无 API」的半截工程。本方案做**双轨补齐**：

- **花销轨（本系统完全掌控，秒级）**：把 gateway 成本计算链接上 `provider_credits`（heygem 的 consumeCoins×汇率），补 lipsync 价目，打通 `actual_cost` 回写。
- **余额轨（受上游限制，分钟级快照、部分平台不可得）**：按「有余额 API / 只有账户级用量 API / 只能看控制台（无 API）」三类分别处理，对第三类引入**本地预扣账估算（local debit ledger）** 兜底并显式标 `estimated`。

最后用一张 **Temporal Schedule（需从零新建调度基建）+ ops 平台总览大盘 + 新建告警评估引擎** 把「准实时看每平台余额与花销、并及时告警管理」闭环。

> **诚实的实时性定义（不夸大）**：**花销秒级**（逐次 `invoke` 落 ledger）；**余额分钟级快照**（后台 5min 刷新 + 前端 30s 轮询 + 手动立即刷新）；其中 **BSS 账单口径本身可滞后约 1 小时、控制台用量页同样有约 1 小时延迟**。所以这是「准实时观测」，不是「余额秒级精确对账」。UI 文案与运营预期都要按这个口径设。

---

## 2. 目标与范围：两条数据轨 + 余额三分类

把用户口语里的「实时看余额和花销」拆成两条可得性天差地别、必须分开承诺的轨：

| 维度 | 定义 | 数据源 | 实时性本质 |
|---|---|---|---|
| **花销(spend)** | 本系统每次 `gateway.invoke` 累计成本 | 本地 `ProviderInvocation` + `UsageMeterRecord` | **完全掌控，逐次秒级** |
| **余额(balance)** | 平台账户里「还剩多少钱/配额」 | 查**上游账户 API**（无法凭空算） | 受限于上游有无 API + 凭据是否匹配，**部分平台结构性不可得** |

### 2.1 余额三分类（本方案的承诺边界）

不再笼统说「有/没有余额 API」，而是按真实可得性分三类，每类对应不同做法：

| 类别 | 含义 | 本方案做法 | UI 标注 |
|---|---|---|---|
| **A 类：有真·余额 API** | 上游直接返「剩余金额/配额」 | 真 API 适配器，返 `status=ok`，值为平台真值 | 真余额 |
| **B 类：只有账户级用量/账单 API** | 能查账户总额或账单，但**不能按能力拆**、且口径可滞后 | 真 API 拿账户级总额（`status=ok`，标 `account_group` 表「账户共享」）；按能力的细分另用本地预扣账估算 | 账户共享总额 + 估算明细 |
| **C 类：只能看控制台（无任何 API）** | 上游不开放余额查询 | **本地预扣账估算**：`status=estimated`，`detail="按花销倒推，非平台真值"` | 估算余额 |

### 2.2 各平台落位矩阵（已按代码现状校正）

| 平台 / provider | 类别 | 余额做法 | 花销现状与改动 |
|---|---|---|---|
| `runninghub.heygem`（lipsync 主路径） | **A** | `accountStatus` **已返 `remainMoney`（CNY 真值）** → 余额侧**基本不缺**，仅校验 `remainMoney` 缺失时的回退口径 | ❗花销现在=0：插件只填 `provider_credits=consumeCoins`，但 gateway 成本链不消费它 → **本方案核心修复点**（见 §3.2a） |
| `dashscope.*`（ASR/VLM/LLM/Omni/VideoReTalk） | **B** | 装 BSS SDK 走 `QueryAccountBalance` 拿**账户级总额**（AK/SK，非 Bearer）；按能力拆只能本地预扣账估算 | 已有 token/秒计价；补 VideoReTalk seed |
| `minimax`（TTS） | **C** | **纯本地预扣账估算**，`status=estimated` | 已有（0.15 CNY/1k 字符） |
| `openai.image` / neuromash 镜像 | **A（中转）/ C（真 OpenAI）** | neuromash(new-api/one-api) 走 `/v1/dashboard/billing`；命中真 OpenAI 显式 `unsupported`（不当 error 刷红） | 已有（0.4 CNY/张） |
| `deepseek` / `kimi` | **A** | `/user/balance`、`/v1/users/me/balance` 适配器已在，补 seed profile 后才出现 | 当前无调用插件，默认不产生花销 |
| 巨量 / OceanEngine（投放） | **A（独立维度）** | P2 单列「投放账户」维度，**不混入 Provider 余额** | 不进 ledger（离线 ETL） |

> ⚠️ 关于 spec §1556「余额=Provider 余额、不含投放账户」：该条款**尚未在仓库中逐字核实**，P2 投放维度是否并入本系统**存疑**。P2 启动前先用 `grep -rn "投放\|advertiser\|1556" docs/` 核实条款真实存在与口径，否则 OceanEngine 单列只是「合理推测」而非「spec 要求」。本方案对此打 **待核实** 标记，不作为硬依据。

**关键承诺**：对 C 类（minimax）我们**不假装能查真余额**，而是引入本地预扣账——运营在 profile 上填充值额度，系统用累计 `estimated_cost` 倒扣，给「估算余额」并明确 `status=estimated`。这是把「查不到真余额」诚实降级为「按花销倒推的估算」，而非留白。

---

## 3. 架构设计

### 3.1 余额刷新

#### (a) 计费配置的承载基座（前置阻断点，必须先做）

❗审查指出的硬阻断：`ProviderProfile`（`providers.py:84`）**只有 `default_options: dict`，没有 `config` 字段**；而 `default_options` 语义是「provider 调用入参」，把汇率/充值额度/中转站类型塞进去会污染插件 invoke 输入。更关键的是 `PatchProviderProfileRequest`/`CreateProviderProfileRequest` **没有任何字段能写这些值**，运营**根本没有 API 入口**填 `topup_amount`/`coin_rate`。所以「本地预扣账」「coins 折算」的存储基座原方案是空想的。

**修法**：新增一个独立的计费配置子模型，并打通可写路径：

```python
# packages/core/contracts/providers.py 新增
class ProviderBillingConfig(ContractModel):
    coin_rate: Money | None = None        # 1 coin / 1 unit_credit 折算的人民币单价
    relay_kind: Literal["new-api", "one-api", "openai"] | None = None
    topup_amount: Money | None = None     # 运营手填：本期充值额度（C/B类预扣账基数）
    topup_at: datetime | None = None      # 本期充值起算时间
    low_threshold: Money | None = None    # 低余额水位（告警用）
```

- `ProviderProfile` 新增 `billing_config: ProviderBillingConfig | None = None`（**独立于 `default_options`**，不污染 invoke 入参）。
- `CreateProviderProfileRequest` 同步新增 `billing_config: ProviderBillingConfig | None = None`。
- `PatchProviderProfileRequest` 同步新增 `billing_config: ProviderBillingConfig | None = None`（可写路径，运营可 PATCH 改充值额度/汇率/水位）。
- `apps/api/services/providers.py` 的 patch 处理把 `billing_config` 写进存储层。
- **AK/SK 仍只进 `SecretStore`/`secret_ref`，绝不进 `billing_config` 明文**（汇率/额度/水位不是密钥，可入 config；密钥不可）。

#### (b) 补齐 balance 适配器（`packages/ops/balance/providers/`）

| 适配器 | 现状（已核实） | 改动 |
|---|---|---|
| `heygem.py` | **已读 `remainMoney` 并按 CNY 返真余额**（`heygem.py:28`），并附带 `remainCoins` 作 quota | **余额侧基本不动**；仅在 `remainMoney` 缺失而只有 `remainCoins` 时，可选用 `billing_config.coin_rate` 把 coins 折成 CNY 兜底（非主路径） |
| `aliyun_bss.py` | SDK 未装 → 恒 unsupported | 把 `alibabacloud_bss20171214` 加进 **可选 extra**（不进默认 dev）；读 `secret_ref` 解出的 **AK/SK**；调 `QueryAccountBalance`（无参）拿账户级总额；返 `account_group="dashscope-account"` 表「账户共享、不可按能力拆」 |
| `openai_relay.py` | 命中真 OpenAI 返 HTML→error | 读 `billing_config.relay_kind`：`openai` 直接返 `unsupported`；`new-api`/`one-api` 走 `/v1/dashboard/billing/subscription`（neuromash 镜像字段需实测） |
| `minimax.py` | 结构性恒 unsupported | 改走**本地预扣账**（见下），返 `status=estimated` |
| `deepseek.py`/`kimi.py` | 有适配器无 profile | 适配器保留；P1 补 seed profile 后自动生效 |
| **新增 `local_debit.py`** | — | 通用本地预扣账后备：`topup_amount - Σestimated_cost(本期)`，任何 C 类或 B 类「按能力拆」都能挂 |

#### (c) 本地预扣账（local debit ledger）——C 类的核心补丁

- 基数来自 §3.1(a) 的 `billing_config.topup_amount` / `topup_at`（运营手填，代表「这次充了多少 / 从何时起算」）。
- `local_debit.py`：`balance = topup_amount - sum(estimated_cost where checked_at >= topup_at)`，SQL 直接在 `provider_invocations` 上按 `provider_id` 聚合。
- 注册策略（`registry.py`）：**真 API 适配器优先**；真 API 返 `unsupported/error` 且 profile 配了 `topup_amount` → fallback 到 `local_debit`，`status="estimated"`、`detail="按花销倒推，非平台真值"`。
- B 类 dashscope 可**两个数都给**：BSS 账户级总额（粗，`account_group=dashscope-account`）+ local_debit 按能力拆（细，estimated）。UI 明示二者口径不同。

#### (d) 定时刷新：Temporal Schedule（**从零新建调度基建，非复用**）

❗审查纠偏：`packages/core/workflow/temporal_adapter.py` **只有 `DigitalHumanVideoWorkflow` + `temporal_workflows()`/`temporal_activities()` 注册列表，完全没有 Schedule 能力**。所谓「Temporal adapter 存在」为真，但「已有 Schedule、只需加一个」是夸大——实为从零写 client.create_schedule + worker 侧注册 + 一个新 workflow/activity。工作量按「新建基建」估，不按「复用」估。

具体落到文件：

1. **在 `temporal_adapter.py` 新增** `refresh_balances` 的 `@workflow.defn` + `@activity.defn`：
   - activity `refresh_balances_activity`：调既有 `service.refresh_balances()`，把结果 upsert 进 `provider_balance_snapshots`；并在其后触发告警评估（§3.3）。
   - 把新 workflow 加进 `temporal_workflows()` 返回列表、新 activity 加进 `temporal_activities()` 返回列表（这两个注册函数已存在，扩展即可）。
2. **在 `apps/worker` 启动处**用 `temporalio` 的 `Client.create_schedule` 创建/幂等更新 `balance-refresh-schedule`，周期 **5 分钟**（可经 `CUTAGENT_BALANCE_REFRESH_INTERVAL` 调）。
   - **幂等策略（补遗漏）**：worker 启动时按固定 `schedule_id="balance-refresh-schedule"` 调 `create_schedule`；捕获 `ScheduleAlreadyRunningError`/already-exists → 改调 `handle.update(...)` 用最新 interval/参数覆盖（update-or-create）。已存在时**不重复创建**、不报错退出。
3. **保留 `BalancePollerService`（`service.py` 现有）作为无 Temporal 的本地 dev 降级路径**；生产以 Schedule 为准。
4. `POST /api/providers/balances/refresh`（`providers.py:118`，已存在）保留作「立即刷新」同步路径。

**双写去重闸门（补遗漏 — 谁赢、幂等键）**：

- 新增 `CUTAGENT_BALANCE_SCHEDULE_ENABLED`（Schedule 总开关）与现有 `poller_enabled`（`settings.py` 已有）。
- **互斥规则**：`CUTAGENT_BALANCE_SCHEDULE_ENABLED=1` 时，**进程内 poller 强制不启动**（Schedule 赢，poller 让位），即便 `poller_enabled=1`。代码层在 poller 启动处加 `if settings.balance_schedule_enabled: return`。生产二选一、永不双开。
- **upsert 幂等键**：`provider_balance_snapshots` 的 upsert 以 `(provider_id, account_group)` 为冲突键，每次刷新**覆盖同一行的最新值**（快照表只留「当前值」语义；历史另由 `checked_at` 时序保留或不保留，按现有 service 行为对齐）。这样即便偶发双写，也只是后者覆盖前者同一行，不产生重复行。

#### (e) 前端刷新

大盘默认 **30s 轮询** `GET /api/providers/balances`（读快照，廉价）；「立即刷新」按钮打 refresh 端点。**不引入 SSE/WebSocket**——余额是慢变量（且 BSS 口径可滞后 1h），5min 后台 + 30s 前端轮询 + 手动刷新已满足「准实时」，SSE 复杂度不划算（本仓库无现成 SSE 基建）。

### 3.2 花销计量

#### (a) ❗核心修复：成本链接上 `provider_credits`（heygem 花销恒 0 的真根因）

已核实：runninghub 插件（`packages/ai/providers/runninghub.py:107`）把 `consumeCoins` 填进 `ProviderResult.provider_credits`，但 gateway 的 `_estimated_cost_from_usage`（`provider_gateway.py:424-439`）**只看 `result.estimated_cost` 与 price_items 的 token/秒/张，完全不消费 `provider_credits`**。所以补再多 `media_second` seed 价目也接不上 coins 计量。

**两选一（推荐组合）**：

1. **在 `_estimated_cost_from_usage` 新增 `provider_credit` 折算分支**：当 `result.provider_credits` 非空且命中 `unit="provider_credit"` 的 price item 时，`amount += item.unit_price.amount * result.provider_credits`（`unit_price` 即 coin→CNY 汇率）。
2. 新增 `ProviderPriceItem.unit` 的 Literal 值 `"provider_credit"`（当前是 `input_token/output_token/media_second/call`，**追加枚举值，向后兼容**）。
3. heygem 走「credits×汇率」这条；汇率来源优先 `billing_config.coin_rate`，否则 seed 的 `provider_credit` price item。

> 这样 heygem 花销从「恒 0」变为「consumeCoins × 汇率」的真实值，且无需依赖插件回填 `estimated_cost`（插件现状没填）。

#### (b) 单价来源策略（优先级链，校正后）

1. provider 自报 `result.estimated_cost`（若插件填了）；
2. **`provider_credits` × `provider_credit` 单价**（heygem 走这条，§3.2a 新增）；
3. `ProviderPriceItem`（seed 价目，token/秒/张/call）；
4. 都没有 → 落 `billing_status="unpriced"` + `cost.unpriced` 告警（已有）。

**补 lipsync 价目**：`provider_seed.py` 给 `runninghub.heygem` 加 `unit="provider_credit"` 的 seed price item（承载 coin 汇率），给 `dashscope.videoretalk` 加 `media_second`/`call` seed。

#### (c) `actual_cost` 回写（打通「真实花了多少」）

- 已核实契约 `ProviderUsageReport.actual_cost` 等字段存在，但 invocation 行的 `actual_cost`/`cost_variance` **全仓无写回**，`cost_variance` 恒 None。
- `gateway.invoke` 当 provider 响应带真实计费字段（heygem consumeCoins、neuromash usage、BSS 对账）时，写 `ProviderInvocation.actual_cost`，并算 `cost_variance = actual - estimated`。
- `reconcile_billing` 增强：不仅用快照首尾差兜底，且把 actual **回写到 invocation**（当前只算不回写）。

#### (d) rollup

复用既有 `GET /api/ops/cost-rollups`、`cost-metrics`，按 `provider_id / capability_id / 时间窗` GROUP BY 已实时；大盘新增 `actual` vs `estimated` 两列对比。

### 3.3 告警评估引擎（**新建，确认不存在**）

已核实 `packages/ops/alert_rules.py` **不存在**；`Budget`/`OpsAlertRule` 有库表+CRUD，但无评估引擎；`ProviderBalanceItem` 连阈值字段都没有（本方案 §3.1a 的 `billing_config.low_threshold` + §4 契约 `low_threshold` 补上）。

- **新增 `packages/ops/alert_rules.py` 评估引擎**，挂在 `refresh_balances_activity` 之后（或独立 Schedule）周期评估：
  - **低余额**：`balance < low_threshold`（threshold 来自 `billing_config.low_threshold`）→ 发 `OpsAlertEvent(code="provider.low_balance", severity=warning/critical)`。estimated 余额触发时 severity 上限设 warning（估算不当 critical 刷红）。
  - **当日花销超预算**：复用 `BudgetEvaluation`（已有 `ratio/threshold_crossed/exceeded`），`threshold_crossed`→warning，`exceeded`→critical，发 `OpsAlertEvent(code="budget.exceeded")`。
- **告警去重**：同 `(code, provider_id)` 在 open 状态期间不重复发（查 `ops_alert_events` open 记录）。

---

## 4. 数据契约改动（contract-first）

**`packages/core/contracts/providers.py`**：

- **新增 `ProviderBillingConfig` 子模型**（见 §3.1a：`coin_rate/relay_kind/topup_amount/topup_at/low_threshold`）。
- `ProviderProfile` 新增 `billing_config: ProviderBillingConfig | None`；`CreateProviderProfileRequest`、`PatchProviderProfileRequest` **同步新增可写 `billing_config`**（否则运营无 API 入口）。
- `ProviderPriceItem.unit` Literal **追加** `"provider_credit"`（向后兼容追加值）。
- `ProviderBalanceItem` **与** `ProviderBalanceSnapshot` **两处同步**新增：
  - `low_threshold: Money | None`、`currency: str | None`、`balance_cny: Money | None`、`spend_today: Money | None`、`spend_month: Money | None`。
  - ⚠️ **`status` 的 Literal 是破坏性联动变更**：当前 `ok/unconfigured/unsupported/unauthorized/error/pending`，要**在两个模型同处追加 `"estimated"`**。这属**纯追加枚举值，向后兼容**（旧快照 status 值不受影响），但 **schema.d.ts 重生成是强制项**，且前端灯色规则要处理 `estimated` 分支。

**`packages/core/contracts/ops.py`**：

- `OpsAlertEvent.code` 文档补新码 `provider.low_balance` / `budget.exceeded`（code 是 str，无需改类型）。
- 新增 `PlatformOverviewRow` / `PlatformOverviewReport`（每平台余额 + 今日/本月花销 + 灯色 + 最后刷新），供 `GET /api/ops/platform-overview`。

**迁移**（`packages/core/storage/alembic/versions/`，接在 `0020` 后）：

- `0021_balance_thresholds_and_actual_cost.py`：
  - `provider_balance_snapshots` 加 `low_threshold/currency/balance_cny`；
  - `provider_invocations` 确认/补 `actual_cost/cost_variance` 列可写；
  - provider profile 存储层加 `billing_config`（JSON 列）；
  - **`status` 枚举处理**：若 status 在 DB 是 varchar/text（非 PG enum 类型）则**无需改列**，纯应用层追加；若是 PG enum 则迁移里 `ALTER TYPE ... ADD VALUE 'estimated'`。**旧行 status 值不受影响**，迁移注释写清「纯追加，不回填、不动旧行」。

**重生成（强制）**：

```bash
python scripts/export_openapi.py && (cd apps/web && npm run generate:api)
```

⚠️ memory 记录：**本地 regen key-order 受 pydantic/Python 版本影响易假漂移，以 CI pinned venv 为准**——不要本地 regen 去「修」别人 PR 的漂移。但**本 PR 自己新增字段后必须重生成并提交生成物**，CI 漂移校验才会绿。

---

## 5. Web 看板（`apps/web/src/pages/ops/`）

新增首屏可见的 **「平台总览（Platform Overview）」** 页（从 `/analytics` 深埋 tab 提升为 ops 一级页），权限放宽到 **operator+viewer 可看**（refresh 仍限 operator）。

**布局**：顶部一排归一总余额卡（全平台 `balance_cny` 求和，标「含估算」）；下方一表，每行一平台：

| 平台 | 余额（原币 + ≈CNY） | 状态灯 | 今日花销 | 本月花销 | 估算/实际 | 最后刷新 | 操作 |
|---|---|---|---|---|---|---|---|
| runninghub.heygem | ¥84（真值, remainMoney） | 🟢 | ¥12.3 | ¥340 | est→actual | 2分钟前 | [刷新] |
| dashscope（账户） | ¥520（账户共享总额） | 🟡 低于水位 | ¥45.1 | ¥1200 | est | 2分钟前（BSS口径可滞后~1h） | [刷新] |
| minimax | ¥30（估算） | 🟡 估算 | ¥3.2 | ¥88 | est | — | — |
| openai.image | unsupported（真 OpenAI） | ⚪ | ¥0.8 | ¥22 | est | — | — |

**灯色规则（含 estimated 分支）**：🟢 `status=ok 且 balance ≥ low_threshold`；🟡 `< threshold` 或 `status ∈ {estimated, unsupported}`；🔴 `balance ≤ 0` 或 `status=error`；⚪ `unsupported/unconfigured`（无法判断）。
**刷新**：30s 轮询 + 右上「全部刷新」+ 每行「刷新」。B 类（dashscope）行上标注「账户共享总额，口径可滞后约 1 小时」。
**改动文件**：新增 `apps/web/src/pages/ops/PlatformOverviewPage.tsx` + `components/ops/PlatformOverviewTable.tsx`；`App.tsx` 加路由 + viewer 放宽；现有 `BalanceQuotaTab.tsx` 复用数据 hook。

---

## 6. 分期实施

### P0 — 让「花销真实、heygem 余额本就可信、能告警」（最高 ROI）

**交付物**：heygem 花销不再恒 0（成本链接上 `provider_credits`）；lipsync 价目补齐；`actual_cost` 回写；低余额+超预算告警上线；大盘页可看。
**改动文件**：

- 契约：`providers.py` 新增 `ProviderBillingConfig` + profile/create/patch 三处 `billing_config` + `ProviderPriceItem.unit` 加 `provider_credit` + balance 两模型加字段（含 `estimated`）；`ops.py` 加 `PlatformOverviewRow/Report`
- `packages/ai/gateway/provider_gateway.py`（`_estimated_cost_from_usage` 加 `provider_credit` 分支；写 `actual_cost`/`cost_variance`）
- `packages/core/storage/provider_seed.py`（heygem `provider_credit` price item + videoretalk seed）
- **新增** `packages/ops/alert_rules.py`（low_balance + budget 评估 + 去重）+ 接进 `apps/api/routers/ops.py`
- `apps/api/services/providers.py`（patch 写 `billing_config`）
- 迁移 `0021_*` + **重生成 openapi/schema.d.ts**
- 新增 `apps/web/src/pages/ops/PlatformOverviewPage.tsx`

**验证**：`python -m pytest tests/ops -q`（余额估算/告警去重/`provider_credit` 折算单测）；新增 `tests/ops/test_alert_rules.py` + `tests/ai/test_gateway_provider_credit_cost.py`；真 provider 用 `runninghub.heygem` 跑一次成片，确认 heygem 花销 = consumeCoins×汇率（非 0）、`actual_cost` 落库。⚠️ 改了 gateway/seed 必须**重启 worker**。

### P1 — 让「主成本大头有余额数字 + 定时刷新真自动」

**交付物**：dashscope BSS 账户余额可查；本地预扣账兜底覆盖 minimax/dashscope 按能力拆；Temporal Schedule 5min 自动刷新（含幂等创建 + 双写闸门）；deepseek/kimi 补 seed profile。
**改动文件**：

- `pyproject.toml`（`alibabacloud_bss20171214` 进**可选 extra**，不进默认 dev，避免污染 `pip install -e .[dev]` 体积/离线安装）
- `packages/ops/balance/providers/aliyun_bss.py`（AK/SK + `QueryAccountBalance` 账户级）、**新增** `local_debit.py`、`registry.py`（真 API 优先 + estimated fallback）
- `packages/ops/balance/providers/openai_relay.py`（`relay_kind` 区分）
- **新增 Schedule 基建**：`temporal_adapter.py` 加 `refresh_balances` workflow+activity 并注册进 `temporal_workflows()`/`temporal_activities()`；`apps/worker` 启动处 `Client.create_schedule` 幂等创建（create → already-exists 则 update）；`settings.py` 加 `CUTAGENT_BALANCE_SCHEDULE_ENABLED`/`_INTERVAL`，并在 poller 启动处加 `if schedule_enabled: return` 互斥闸门
- `provider_seed.py`（deepseek/kimi profile）

**验证**：`pytest tests/ops`；Schedule 幂等单测（重复 create 不报错）；双写闸门单测（schedule_enabled 时 poller 不启）；Temporal 测试指向**共享 MinIO ephemeral 桶**（memory 坑）。**BSS 真凭据验证标为「手动/线下」**——CI/沙箱无真 AK/SK，门禁里 BSS 适配器只跑 mock/unsupported 路径单测，不在 `ci_gate` 自动跑真查询。`scripts/ci_gate.sh` 全绿（PG 55432 + Temporal 7233 + MinIO）。

### P2 — 投放平台 + 单位归一 + 大盘打磨

**前置**：先 `grep -rn` 核实 spec §1556「余额不含投放账户」条款真实存在再启动（见 §2.1 待核实标记）。
**交付物**：巨量 OceanEngine 投放账户余额/消耗单列；跨平台 CNY 归一；权限分层。
**改动文件**：

- **新增** `packages/ops/balance/providers/oceanengine.py`（`advertiser/fund/get` + `report/advertiser/get`，OAuth2 token 进 SecretStore）；大盘加「投放账户」分区（与 Provider 余额并列、明确区分）
- 归一汇率表（coins/USD→CNY）进 `settings` 或 `provider_seed`
- `App.tsx` viewer 放宽

**验证**：`pytest`；OceanEngine 用沙箱 advertiser_id 验 OAuth2；前端 e2e 看灯色/归一。

---

## 7. 风险与坑

1. **计费配置无承载基座（最高优先级前置）**：`ProviderProfile` 无 `config`、`default_options` 是 invoke 入参不能塞。必须先新增 `billing_config` 子模型 + create/patch 可写路径 + 迁移列，否则预扣账/汇率全是空想（§3.1a）。
2. **heygem 花销恒 0 的真根因不是「没汇率」而是「成本链没接 `provider_credits`」**：插件已填 credits，gateway 不消费。修 `_estimated_cost_from_usage` 加 `provider_credit` 分支，否则补再多 `media_second` seed 也接不上（§3.2a）。
3. **heygem 余额本就是真值**：`remainMoney` 已按 CNY 返回，余额侧不要重复造「coins→CNY」轮子（仅作 remainMoney 缺失兜底）。
4. **Temporal Schedule 是从零新建基建**：`temporal_adapter.py` 无 Schedule 能力，要新写 workflow/activity + worker 侧 `create_schedule`，工作量按新建估；**幂等**用 create→already-exists 则 update。
5. **双写去重要有硬闸门**：`CUTAGENT_BALANCE_SCHEDULE_ENABLED=1` 时 poller 强制让位；upsert 以 `(provider_id, account_group)` 为冲突键，避免重复行（§3.1d）。
6. **AK/SK vs Bearer 鉴权割裂**：dashscope 余额走 BSS 需主账号 AK/SK，与调用的 Bearer 是两套；都只进 SecretStore，绝不进 config 明文/env。
7. **BSS 只给账户级总额且口径可滞后~1h**：UI 标「账户共享」+「口径可滞后约 1 小时」，按能力细分只能 estimated，不能宣称平台真值。
8. **BSS SDK 进可选 extra**：不进默认 dev，避免污染安装体积/离线安装；CI 走 mock/unsupported，真凭据验证手动/线下。
9. **中转站 billing / 真 OpenAI**：`/v1/dashboard/billing` 仅 new-api/one-api 可信；真 OpenAI 返 HTML 要**显式 `unsupported`**（别刷红）；neuromash 字段需实测。
10. **`status` 加 `estimated` 是两模型 + 生成物联动**：`ProviderBalanceItem` 与 `ProviderBalanceSnapshot` 两处同步；纯追加枚举、旧行不受影响；schema.d.ts 必重生成；前端灯色处理 estimated。
11. **估算 ≠ 实际**：预扣账、unpriced 0 元、汇率漂移都会偏差。UI 用 `status=estimated` + est/actual 列**诚实标注**，不让运营误以为精确对账。
12. **worker 是独立长驻进程**：改 `provider_gateway`/`provider_seed`/节点代码后**必须重启 worker**（memory 反复踩）。
13. **上游限频**：5min × 8 provider 压力小，但 BSS/OceanEngine 有 QPS 限制，activity 内串行 + 失败优雅降级（沿用「poller 永不抛异常」纪律），失败写 `status=error` 而非崩刷新链。
14. **OpenAPI 漂移假阳性**：本 PR 自己改字段后必须 CI venv 重生成并提交；但别本地 regen 去「修」别人 PR 的漂移（key-order 环境敏感，memory 明确记过）。
15. **spec §1556 自引未核实**：P2 投放维度并入与否，启动前先 grep 核实条款再决策。
16. **「实时」措辞**：对外统一说「准实时（花销秒级 / 余额分钟级快照，BSS 口径可滞后~1h）」，避免运营误期望余额秒级精确。

---

**相关文件路径（均绝对，已核实存在性）**：

- 余额适配器目录：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/providers/`（现有 `heygem.py`；**新增** `local_debit.py`、`oceanengine.py`、`registry.py` 扩展）
- 余额 base/service：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/base.py`、`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/service.py`
- 评估引擎（**新增，确认不存在**）：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/alert_rules.py`
- 网关成本链（**核心修复点**）：`/Users/yoryon/Projects/cutagent-genesis/packages/ai/gateway/provider_gateway.py`（`_estimated_cost_from_usage` 在 424-439 行；invoke 计费段 ~299-326 行）
- runninghub 插件（已填 `provider_credits`）：`/Users/yoryon/Projects/cutagent-genesis/packages/ai/providers/runninghub.py`（107 行）
- 价目 seed：`/Users/yoryon/Projects/cutagent-genesis/packages/core/storage/provider_seed.py`
- 契约：`/Users/yoryon/Projects/cutagent-genesis/packages/core/contracts/providers.py`（ProviderProfile:84 / ProviderBalanceItem:198 / Snapshot:218 / PriceItem.unit）、`/Users/yoryon/Projects/cutagent-genesis/packages/core/contracts/ops.py`
- 迁移（**新增**）：`/Users/yoryon/Projects/cutagent-genesis/packages/core/storage/alembic/versions/0021_balance_thresholds_and_actual_cost.py`
- Temporal 调度（**从零新建 Schedule**）：`/Users/yoryon/Projects/cutagent-genesis/packages/core/workflow/temporal_adapter.py`（现有 `temporal_workflows()`:97 / `temporal_activities()`:101 / `DigitalHumanVideoWorkflow`:119）、`/Users/yoryon/Projects/cutagent-genesis/apps/worker/`（启动处 `create_schedule`）
- settings：`/Users/yoryon/Projects/cutagent-genesis/packages/core/config/settings.py`（现有 `poller_enabled`；新增 `balance_schedule_enabled`/`_interval`）
- 路由：`/Users/yoryon/Projects/cutagent-genesis/apps/api/routers/providers.py`（balances/refresh:118）、`/Users/yoryon/Projects/cutagent-genesis/apps/api/routers/ops.py`、`/Users/yoryon/Projects/cutagent-genesis/apps/api/services/providers.py`（patch 写 billing_config）
- 前端（**新增**）：`/Users/yoryon/Projects/cutagent-genesis/apps/web/src/pages/ops/PlatformOverviewPage.tsx`、`/Users/yoryon/Projects/cutagent-genesis/apps/web/src/components/ops/PlatformOverviewTable.tsx`