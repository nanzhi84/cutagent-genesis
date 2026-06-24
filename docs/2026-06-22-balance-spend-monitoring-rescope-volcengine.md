# 树影 Cutagent · 平台余额&花销监控（收窄版 · minimax→火山引擎）

> 2026-06-22 第二轮调研。收窄到真实调用 provider，TTS 换火山。9-agent 工作流（5 路火山官方文档联网核实 + 对抗式审查 + 主作者复核），CC 独立核验了 voice-sync 链路/netpolicy/成本链 bug 等代码事实全部属实。

## 火山引擎接口可行性结论（你问的「这两个接口」）

**① 余额查询：有，真账户级 API。**

有，真账户级余额 API。Action=QueryBalanceAcct，Service=billing，Version=2022-01-01，host=open.volcengineapi.com（或 billing.volcengineapi.com），鉴权 AK/SK + 火山 V4 签名（HMAC-SHA256）。返回 AvailableBalance/CashBalance/ArrearsBalance/FreezeAmount/CreditLimit/AccountID（CNY，金额为字符串，AccountID 为整型）。置信度：高（官方文档 6269/130258-130259 + 官方 SDK volcenginesdkbilling 的 query_balance_acct + 第三方 Go 客户端 starudream/sign-task 三处交叉印证字段稳定）。口径延迟：余额属资金账户即时快照，经验近实时，但官方文档未明文承诺实时口径，严格说标 unknown（不要当成已证实的实时）。粒度限制：账户级总余额，不按产品/能力拆——火山 TTS 与方舟 Seedance 同属一个火山账户，一次查询返回的是两者（及该账户其他服务）合并的总余额。这与 aliyun_bss 的 QueryAccountBalance 定位完全对等，可仿写一个真 poller（A 类）。

**② 用量/账单查询：有，能按产品拆，但只到月账期、T+1。**

有，且能按产品拆。账单类 Action：ListBillOverviewByProd（按产品汇总，每产品每账期一行，可传 Product 数组过滤）、ListBillDetail（按计费项 Element/服务 + 实例 + 可按天 GroupPeriod=1 拆，含 Count/Unit/UseDuration 用量字段）、ListBillOverviewByCategory、ListBill。同 Service=billing/Version=2022-01-01/AK-SK 签名，无需申请，5 QPS/账户，置信度高。但口径延迟是硬约束且不可绕：账期粒度只到月（BillPeriod=YYYY-MM），没有"今天 TTS 花了多少"的实时单产品接口；当月数据 T+1 增量投递，月汇总建议次月第4自然日 10 点后拉，分账/成本明细 T+2~T+4。能否按 TTS vs Seedance 拆：能拆到产品维度，但确切 Product/ProductZh 取值（"语音技术/语音合成"与"火山方舟"）文档示例未给（只给 ECS/auto_test），且 Seedance 与 ARK 大模型很可能同归"火山方舟"一个 Product 下，需先在真实账户跑一次 ListBillOverviewByProd 看实际 Product 值、再靠 ListBillDetail 的 Element 进一步区分（这一步置信度 medium，必须实测）。结论：账单 API 适合月度按产品对账，不适合实时花销监控。

## 收窄覆盖矩阵（只剩真实调用）

| 平台/provider | 能力 | 余额等级 | 余额怎么查 | 花销怎么得 | 要做什么 |
|---|---|---|---|---|---|
| 火山引擎 TTS（volc.tts，capability tts.speech， | 语音合成（数字人配音） | A-真余额API | QueryBalanceAcct（Action=QueryBalanceAcct, Service=billing, Version=202 | 本地逐次 ledger 估算：TTS 合成响应只回 base64 音频+reqid，无任何计费用量字段，拿不到真值。按字符计费（万字符结算） | 1) provider_seed 把 minimax.tts.prod 换成 volc.tts.prod（capability 仍 tts.speech），新写 |
| 火山方舟 Seedance（ark/seedance，文/图生视频，新增中，与  | 文/图生视频（B-roll/封面动态 | A-真余额API | 同上 QueryBalanceAcct（与 TTS 共账户，一个火山 poller 全覆盖，余额合并不可拆产品）。 | 本地逐次 ledger（且能拿真 token 数）：Ark 任务 GET 响应带 usage={completion_tokens,tota | 1) Seedance provider 把响应 usage.total_tokens 透传进 ProviderResult.raw_usage/provide |
| dashscope 账户（阿里云百炼：asr/vlm/llm/omni=audi | 语音转写/视觉标注/文本生成/音频理 | B-账户级API | 已有 AliyunBssPoller（prefixes=aliyun/dashscope/qwen/bailian），走 alibabacl | 本地逐次 ledger：dashscope 各能力调用经 gateway 落 ProviderInvocation.estimated_co | pip 装 alibabacloud_bss_open_api + alibabacloud_tea_openapi（可选依赖，建议 extras），余额 po |
| runninghub.heygem（lipsync.video 主路） | 口型驱动（数字人对口型，主路） | A-真余额API | 已有 HeyGemPoller，POST /uc/openapi/accountStatus，返回 remainMoney(CNY 真值)+ | 现状=花销恒 0（坑）：runninghub provider 回了 provider_credits，但 gateway 的 _estim | 修 gateway 成本链：让 _estimated_cost_from_usage(或上游)消费 result.provider_credits（heygem |
| openai.image / neuromash 镜像（image.genera | 封面图/图像生成 | B-账户级API | 已有 OpenAIRelayPoller（prefixes=openai），读中转站 /v1/dashboard/billing/{subs | 本地逐次 ledger：openai_image provider 回 provider_credits=cost_per_image×co | 同 heygem：修 gateway 让其消费 provider_credits；余额 poller 已就绪（依赖中转站口径，真 OpenAI 不可用）。 |

## 总评

收窄后整体高度可行，且换火山对'看余额'是实打实的利好。"换火山后 TTS 余额从 C(估算)升到 A/B(真API)"这个判断成立但要精确表述：升的是'余额可见性'到 A 类真 API（火山 QueryBalanceAcct 返回真 CNY 可用余额），而'花销'仍是 B/本地估算口径——火山 TTS 响应不回计费字段，逐次只能按字符×单价估，真值得靠 T+1 账单对账。相比之下原 minimax 同样是按字符估算且余额可见性更弱，所以换火山在余额侧确有净提升。收窄后 6 个真实 provider 里，余额真 API（A）覆盖火山(TTS+Seedance 共账户一个 poller)、heygem；账户级 API（B）覆盖 dashscope(BSS,SDK 未装需 pip 激活)、openai 中转站；没有纯 C(只能估算)的余额死角，余额面板可做到全覆盖。最大的真实工程缺口不在火山而在存量成本链 bug：gateway 的 _estimated_cost_from_usage 只认四种 token/second/call 单位、根本不消费 provider_credits，导致 heygem 与 openai.image 这两个已回真 credits 的 provider 花销恒 0——这是'看花销'需求的头号必修项，与换不换火山无关。火山落地的净增量工作量小且清晰：新增一个火山 billing poller(仿 aliyun_bss，建议用 volcengine-python-sdk 的 volcenginesdkbilling 走 SDK 免手写 V4 签名，OPTIONAL import 未装则降级)、netpolicy 加三个 host(openspeech.bytedance.com/ark.cn-beijing.volces.com/open.volcengineapi.com)、TTS provider 换 openspeech 这条线、Seedance 计费从 media_second 改 token 口径。两个必须实测确认的不确定点：火山账单里 TTS 与 Seedance 的确切 Product 取值(很可能 Seedance 与 ARK 同归'火山方舟'需靠 Element 拆)，以及 QueryBalanceAcct 是否真实时(文档未承诺，标 unknown)。共性结构限制要向用户讲清：火山/阿里/openai 的余额都是账户级总额不分产品，所以'每个平台余额'能做到平台级真实，但'每个能力的余额'拆分火山阿里都给不了——按能力归因只能靠本地逐次 ledger 的花销侧，余额侧只能到账户。综上：余额监控可立即做成接近全 A/B；花销监控需先修 provider_credits 成本链 + 给火山/Seedance 配好 token/字符价目，且接受当日实时只有本地估算、真值 T+1。

---
# 平台余额 & 花销监控落地方案（收窄版 · minimax→火山引擎 · 精修终稿）

## 0. 一句话结论 + 范围声明

**一句话**：本次把监控范围砍到 6 个真实会被调用的 provider，并把 TTS 从 minimax 换成火山引擎；换型后**余额面板可立即做到全 A/B 覆盖（无纯估算死角）**。但真正卡脖子的不是火山，而是存量的 `_estimated_cost_from_usage` 成本链 bug——它不消费 `provider_credits`，导致 heygem 和 openai.image 这两个已回真 credits 的 provider 花销恒 0，这是「看花销」需求的头号必修项，与换不换火山无关。**此外，minimax 换型不是「只换合成插件」这么简单：minimax 插件还承载账户音色同步/克隆/试听，被 `apps/api/services/voices.py` 的 `sync_voices` 调用，必须显式决策这条链路的去留（§1.3），否则是静默功能回归。**

**纳入监控（收窄后 6 个，按账户归并为 5 个余额账户）**：

| provider_id | 能力 | 余额账户 | 余额等级 |
|---|---|---|---|
| `volcengine.tts`（替换 `minimax.tts`） | tts.speech 数字人配音 | 火山账户（与 Seedance 共享） | A 真 API（**实时性待真凭据冒烟验证**） |
| `volcengine.seedance`（新增中） | 文/图生视频 | 火山账户（同上，一个 poller 全覆盖） | A 真 API（**同上**） |
| `dashscope.{asr,vlm,llm,omni}` + `dashscope.videoretalk` | 转写/标注/文本/音频理解/口型备路 | 阿里云百炼账户（5 能力一账户） | B 账户级 API（BSS SDK 未装） |
| `runninghub.heygem` | lipsync.video 主路 | RunningHub 账户 | A 真 API（remainMoney CNY 真值） |
| `openai.image` / neuromash 镜像 | image.generate 封面图 | 中转站账户 | B 账户级 API（`openai_relay.py` poller，**保留**） |

**明确排除（不接入余额/花销，且删除其 balance poller 注册）**：minimax、deepseek、kimi、巨量/OceanEngine。

**诚实声明（火山调研置信度）**：
- 火山 `QueryBalanceAcct` 余额 API **字段稳定性=高**（官方文档 6269/130258-130259 + 官方 SDK `volcenginesdkbilling` + 第三方 Go 客户端三方交叉印证）。方案**不**把它当既定事实，对两个低置信点诚实标注：
  - **余额实时性口径=unknown**（官方文档未承诺实时）→ 一律标「**待真凭据冒烟验证**」。
  - **TTS / Seedance 在账单里的确切 `Product` 取值=medium**（很可能 Seedance 与 ARK 同归"火山方舟"一个 Product，需靠 `ListBillDetail` 的 `Element` 再拆）→ **必须在真实账户实测**，仅 P2 对账依赖，P0/P1 不阻塞。
- **冒烟通过前，代码 `detail` 里的「待验证」字样、文档/PR 描述里的「待验证」标记，一律不摘；不对用户宣称「实时」。** P1 冒烟脚本必须**真正断言实时性**（下单产生消费后秒级复查余额是否变化），否则「待验证→已验证」的摘标动作会沦为走过场（见 §4 P1 验收门）。

---

## 1. 火山引擎接入（本次新增重点）

### 1.1 火山 TTS 调用插件（替换 minimax 的 `tts.speech` 合成路径）

**新增** `packages/ai/providers/volcengine_tts.py`，仿 `packages/ai/providers/dashscope.py` 的同步合成骨架（TTS 是同步、非 async-job，不需要 `mark_polling`）。

- **走哪条线 + 鉴权差异**：用**语音技术（openspeech 大模型语音合成）**这条线，**不是**走方舟 Ark。
  - host：`openspeech.bytedance.com`，端点 `POST /api/v1/tts`。
  - 鉴权头是火山语音特有的**分号格式** `Authorization: Bearer;{access_token}`（注意分号，不是标准 `Bearer {token}`），请求体带 `app.appid` / `app.cluster`。这与 Ark 的 `Bearer {ARK_API_KEY}` 是两套不同凭证体系，**secret 分开存**（见 1.5）。
  - 响应只回 `data`（base64 音频）+ `reqid`，**无任何计费字段**——花销只能靠字符估算。
- **`ProviderResult` 填法**：把 `len(text)` 填进 `input_tokens`（语义=字符数），复用 gateway 现成的 `input_token` 价目路径（`_estimated_cost_from_usage` 第 429-430 行已支持 `input_token` 单位）。`raw_usage` 存 `reqid` + 字符数便于对账。
- **注册**：在 `packages/ai/providers/__init__.py` 的 `register_real_provider_plugins` 里把 `minimax.tts` 一行替换成 `volcengine.tts`（详见 §1.4 完整 minimax 清理清单）。

**注意坑**：TTS 是音频节点（`packages/production/pipeline/nodes/tts.py`）的上游，换插件后**必须重启 worker**（独立长驻进程），只重启 API 不生效。

### 1.2 火山余额 poller（新增，类比 aliyun_bss.py）

**新增** `packages/ops/balance/providers/volcengine.py`，结构完全照搬 `aliyun_bss.py` 的「OPTIONAL import → 未装则 `_unsupported`」模式（aliyun_bss 已是这个范式的现成模板）：

```
class VolcenginePoller(BasePoller):
    key = "volcengine"
    prefixes = ("volcengine", "volc", "ark")   # 同时覆盖 volcengine.tts 与 volcengine.seedance
```

- **调用方式（优先 SDK 免手写签名）**：OPTIONAL `import volcenginesdkbilling`，调 `query_balance_acct`（`Action=QueryBalanceAcct, Service=billing, Version=2022-01-01`）。SDK 未装 → `_unsupported`（不崩，shape 就绪，和 aliyun_bss 一致）。
- **secret 形式**：火山是 AK/SK 对，沿用 aliyun_bss 的 `"access_key_id:access_key_secret"` 拼接约定，复用其 `_split_credentials` 思路。
- **返回**：`AvailableBalance`（CNY，字符串）→ `money(...)` 落 `balance`；`detail` 标注「账户级总额，与 TTS/Seedance 合并不分产品」。
- **置信度护栏（硬性）**：`detail` 里**写明**「余额实时性 unknown，待真凭据冒烟验证」；冒烟前该 poller 在文档/PR 描述里标 **待验证**，冒烟脚本未真正断言实时性前不得摘标。
- **注册**：在 `packages/ops/balance/registry.py` 的 `build_pollers()` 里改注册（详见 §1.4 完整 minimax 清理清单）。

**依赖进可选 extra**：在 `pyproject.toml` 加 extra（如 `[volcengine]` = `volcengine-python-sdk`），与 `alibabacloud_bss_open_api` 同档处理，**不进默认依赖**，CI 共享 venv 不装也不崩（poller 降级 unsupported）。

### 1.3 【新增 · high】minimax 音色同步链路决策（避免静默功能回归）

**真实情况（已核实）**：minimax 插件 `packages/ai/providers/minimax.py` 不止做 `tts.speech` 合成，还实现了：
- `_voice_list`（第 54 行，`POST /get_voice` 拉账户音色）
- `_clone`（第 203 行，`POST /voice_clone`）
- `_design` / `_preview_voice`（第 237 / 331 行，设计 + 试听）

这些被 `apps/api/services/voices.py` 的 `sync_voices` 调用：该流程 `_select_tts_profile_for_sync` 会挑**任意 enabled、非 sandbox、有插件、有有效密钥的 `tts.speech` profile**，然后 `gateway.invoke(... input={"operation": "voice_list"})`。**若把 gateway 注册从 `MiniMaxTTSProvider` 直接换成只会合成的 `volcengine_tts`，`sync_voices`（同步账户音色到声音库）、音色克隆、试听三个能力会失去 provider 实现**（profile 还在但插件不支持该 operation）——属静默功能回归。

**本方案决策（P0 必须二选一，不能含糊）**：

- **方案 A（推荐 · 先保住功能）**：**保留 `packages/ai/providers/minimax.py` 插件文件**，但**只用于音色同步/克隆/试听，不再用于合成**。具体做法：
  - gateway 注册时，`minimax.tts` 这一 provider_id 继续注册 `MiniMaxTTSProvider`（用于 voice_list/clone/design/preview），但 provider_seed 里 `minimax.tts.prod` profile 的**合成路径不再被流水线选中**（音频节点改走 `volcengine.tts.prod`）。
  - 即「合成换火山、音色同步仍走 minimax」。代价：minimax 账户仍需保留（仅供音色管理），但**其余额/花销不纳入监控**（balance poller 仍删，见 §1.4），账户余额监控缺口在 UI/文档诚实写明「minimax 仅用于音色库管理，不在余额监控范围」。
  - **`packages/ops/balance/providers/minimax.py`（balance poller）照删**——音色同步不需要余额 poller。
- **方案 B（彻底下线 minimax）**：评估火山语音是否有等价「拉账户音色 / 克隆 / 试听」接口（火山音色体系与 minimax 不同，需实测）。
  - **若火山有等价接口** → 在 `volcengine_tts.py` 里**补齐 `list_voices` / `voice_clone` / `preview` operation**，`sync_voices` 无缝切到火山，minimax 两个文件（ai 插件 + balance poller）全删。
  - **若火山无等价接口** → 该能力本就无法平移，必须在方案/文档里**诚实写明「音色库同步/克隆/试听功能随 minimax 下线」**，并清理 `apps/api/services/voices.py` 对应分支（`sync_voices` / `_select_tts_profile_for_sync`）+ 相关路由/前端入口，同时删 minimax 两个文件。

**默认按方案 A 落地**（先不丢功能、改动面最小、解耦火山音色调研）；方案 B 待火山音色接口调研完成后再决，决策结论回写本方案 §1.3。**无论 A/B，§1.4 的 balance poller 与 netpolicy/registry 清理都照做**——它们与音色链路无关。

### 1.4 【精修 · 完整 minimax 清理清单（文件级 + 字段级）】

> 审查指出原方案只点到「profile 和价目」，漏列 concurrency_key、catalog id、price item id，以及两个 minimax 文件的去留、registry 的悬空 import。以下为已核实的**完整**清单。

**(a) provider_seed（`packages/core/storage/provider_seed.py`）四处全改：**
- 第 32-33 行：`id="minimax.tts.prod"` / `provider_id="minimax.tts"` → 新增 `volcengine.tts.prod` / `volcengine.tts`（若按 §1.3 方案 A 保留 minimax 音色，则**保留** `minimax.tts.prod` profile 但仅供音色，**另加** `volcengine.tts.prod` 合成 profile；若方案 B 则替换）。
- 第 38 行：`secret_ref="minimax_prod.secret"` → 合成 profile 改 `secret_ref="volc_tts_prod.secret"`（openspeech appid/token；见 §1.5）。
- 第 39 行：`concurrency_key="minimax:tts.speech"` → 合成 profile 改 `concurrency_key="volcengine:tts.speech"`。
- 第 228 行：`ProviderPriceCatalog(id="price_minimax_prod", provider_id="minimax.tts", ...)` → 新增 `ProviderPriceCatalog(id="price_volcengine_prod", provider_id="volcengine.tts", ...)`（方案 B 替换；方案 A 可留 minimax catalog 或一并清理，按是否还想给音色记账决定，默认清理仅留合成）。
- 第 241-244 行：`price_items["price_minimax_tts_chars"]` / `id="price_minimax_tts_chars"` / `catalog_id="price_minimax_prod"` / `provider_id="minimax.tts"` → 新增 `price_volcengine_tts_chars`（`unit="input_token"`，字符单价；catalog 指向 `price_volcengine_prod`）。

**(b) ai 侧插件文件 `packages/ai/providers/minimax.py`：**
- **方案 A**：**保留**（音色同步仍需）。仅在 `__init__.py` 的合成注册里把 `tts.speech` 默认插件指向 volcengine（minimax 注册保留，供 voice_list/clone/design）。
- **方案 B（火山有音色接口或确认下线）**：**删除整个文件**。

**(c) balance poller 文件 `packages/ops/balance/providers/minimax.py`：无论 A/B 一律删除**（音色同步与余额无关）。

**(d) registry（`packages/ops/balance/registry.py`）—— import 与实例化都要删，别留悬空 import：**
- 删 import：`from .providers.deepseek import DeepSeekPoller`、`from .providers.kimi import KimiPoller`、`from .providers.minimax import MiniMaxPoller`（第 24-26 行三行）。
- `build_pollers()` 删实例化：`DeepSeekPoller()`、`KimiPoller()`、`MiniMaxPoller()`（保留 `OpenAIRelayPoller()`、`HeyGemPoller()`、`AliyunBssPoller()`）。
- **加** `from .providers.volcengine import VolcenginePoller` + `VolcenginePoller()`。
- 同步删掉 registry 模块 docstring 里「e.g. MiniMax is always unsupported」这句过时示例（第 7-8 行附近）。

**(e) 其余 balance poller 文件去留：**
- `packages/ops/balance/providers/deepseek.py`、`kimi.py`：**删除文件**（排除项，不再注册）。
- `packages/ops/balance/providers/openai_relay.py`：**保留**（`openai.image` / neuromash 镜像余额要用，B 级账户余额来源）。
- `packages/ops/balance/providers/aliyun_bss.py`、`heygem.py`：**保留**。

**(f) 测试断言：** 确认 `tests/` 里没有断言 deepseek/kimi/minimax 三个 poller 存在的用例；有则同步改/删。被删 provider 的 profile 若仍在 seed（方案 A 的 minimax 音色 profile），`query_balance` 会回 `unsupported`（不崩，但大盘 realData 过滤掉）。

### 1.5 火山花销（逐次 ledger）

- **TTS**：逐次 `len(text) × 字符单价` 落 `estimated_cost`（走 `input_token` 价目）。严格对齐账单应按 `ceil(utf8_bytes/1024)` 的「次」口径，工程上 P0 先线性近似，P2 用账单对账校准。
- **Seedance**：Ark GET 响应带 `usage.total_tokens`，是上游唯一实时、可归因到 run/case 的真口径。把 `usage.total_tokens` 透传进 `ProviderResult.raw_usage`，并按 **token 单位** 计价（见 §3 单位归一，P2 落地）。
- **可选 actual 对账**：火山账单 API（`ListBillOverviewByProd` / `ListBillDetail`）做月度按产品对账，**仅 P2**，且需先实测 Product 取值（medium 置信度）。

### 1.6 一个火山账户承载 TTS + Seedance

- **余额**：账户级共享总额。两个 profile 都用同一个 `account_group`——在 provider_seed 里给两个 profile 配**同一个 `account_group`** 标识（`ProviderBalanceItem.account_group` 字段第 193 行已存在），余额面板按 `account_group` 去重展示一行。
- **花销**：按能力拆**只能靠本地逐次 ledger**（TTS 按字符、Seedance 按 token），余额侧给不了能力级拆分——这点要在 UI/文档对用户讲清。**注意：余额按 `account_group` 折叠，花销绝不折叠**——前端折叠时不能把 dashscope（5 能力一账户）、volcengine（2 能力一账户）的 per-capability 花销也一起折没（§5.2）。
- **凭证三套分离**（各自进 SecretStore，绝不进 env/代码）：
  - TTS 调用用 openspeech 的 appid + access_token（`volc_tts_prod.secret`）；
  - Seedance 调用用 Ark 的 `ARK_API_KEY`（`volc_ark_prod.secret`）；
  - 余额 poller 用 AK/SK（`volc_billing_prod.secret`）。

### 1.7 netpolicy host 白名单

`packages/ai/netpolicy.py` 的 `DEFAULT_ALLOWED_HOSTS`（第 37-47 行）：
- **加**：`openspeech.bytedance.com`（TTS）、`ark.cn-beijing.volces.com`（Seedance，Seedance 计划已要求）、`open.volcengineapi.com`（余额 API）。
- **删**：`api.minimaxi.com`、`api.deepseek.com`、`api.moonshot.cn`（排除项，第 45 行附近经核实确在白名单）。
  - **方案 A 例外**：若保留 minimax 音色同步，则 `api.minimaxi.com` **不能删**（音色 list/clone/preview 仍要访问该 host）。删 host 前确认 `sync_voices` 是否仍走 minimax；走则保留该 host，仅删 deepseek/moonshot 两个。
- **删 host 后做一致性检查**：grep 确认没有别处（provider_seed / registry config / 前端 dev 配置）还引用被删的三个 host，避免 netpolicy 校验报「缺 host」。
- 确认 OSS presign 域名（`oss-cn-shanghai.aliyuncs.com` 等）已在白名单（videoretalk / Seedance 参考图 presign 用）。

---

## 2. 沿用上轮已验证的硬骨头（重点标改动文件）

### 2.1 【头号必修】heygem / openai.image 花销修复——成本链消费 provider_credits

**根因（已在 `packages/ai/gateway/provider_gateway.py` 第 424-439 行核实）**：`_estimated_cost_from_usage` 只认 `input_token/output_token/media_second/call` 四种单位，**完全不读 `result.provider_credits`**（契约第 31 行该字段存在），导致 runninghub/openai_image 回的真 credits 进了 `UsageMeterRecord.provider_credits`（第 312 行存了）却从不参与 `estimated_cost` 计算 → 花销恒 0。

**改动（三步齐全）**：
1. 契约 `packages/core/contracts/providers.py` 第 150 行：`ProviderPriceItem.unit` 的 `Literal` **追加 `"provider_credit"`**。
2. gateway 第 428-436 行循环里**加分支**：
   ```python
   elif item.unit == "provider_credit" and result.provider_credits is not None:
       amount += item.unit_price.amount * result.provider_credits
   ```
   （单价=每 credit 折多少钱；heygem 已回 coins/credits，openai_image 回 `cost_per_image×count`。）
3. `packages/core/storage/provider_seed.py` 给 `runninghub.heygem`、`openai.image` 各加 `ProviderPriceCatalog` + `ProviderPriceItem(unit="provider_credit", ...)`，否则继续记 `cost.unpriced` 告警。

> 改 `ProviderPriceItem.unit` Literal 属契约形状变更，**必须**按 CLAUDE.md 重生成 `openapi.json` + `schema.d.ts`（§3 已列）。此条排 P0 头号必修、且与火山换型解耦。

### 2.2 actual_cost 回写

`ProviderInvocation.actual_cost` 字段已存在（第 53 行）但无写回路径。在 `packages/ops/` 新增对账写回：reconcile 流程（`ReconcileBillingRequest/Response` 契约第 223-245 行已就绪）拉账单后把真值写回 `actual_cost`，并把 `billing_status` 从 `estimated` 推进到 `reconciled`（第 47 行 Literal 已含 `reconciled`，普通字段，无需 `assert_transition`）。

### 2.3 新建 alert_rules.py（低余额 + 超预算告警）

- **超预算**：`packages/ops/budget_evaluation.py` 已实现 `evaluate_budget`（75/90% 阈值），**复用**，只需把余额面板/花销聚合接进去。
- **新增** `packages/ops/alert_rules.py`：低余额规则（`ProviderBalanceItem.balance < 阈值` → `OpsAlertEvent`，code=`balance.low`），与现有 `cost.unpriced`（gateway 第 455 行）/预算告警走同一 `OpsAlertEvent` 通道。

### 2.4 ProviderBillingConfig 计费配置基座（可写）

新增契约 `ProviderBillingConfig`（计费配置：单价档位、低余额阈值、预算）+ profile/create/patch 端点，挂在 `apps/api/routers/ops.py` 或 `providers.py`。让运营能改火山字符单价、Seedance token 单价、低余额阈值，而不必改代码/seed。

### 2.5 dashscope 走 BSS

`packages/ops/balance/providers/aliyun_bss.py` 已就绪（经核实 `prefixes=('aliyun','dashscope','qwen','bailian')` 已含 dashscope），现降级 `unsupported`。只需 `pip install alibabacloud_bss_open_api alibabacloud_tea_openapi`（进可选 extra），余额 poller 即激活。dashscope 5 能力共一个账户、共一个 `dashscope_prod.secret`，余额按 `account_group` 归一行。

### 2.6 Temporal Schedule 定时刷新（从零建 · 精修幂等/互斥/限流落点）

> 审查指出原方案只在文字层声称「含幂等 + 互斥」，未给落地机制，且进程内 asyncio lock 在多 worker 下无效。以下补齐具体落点。

- 现有 `BalancePollerService`（`packages/ops/balance/service.py`）是 **asyncio 进程内** 轮询、默认 OFF。生产改用 **Temporal Schedule** 驱动（`packages/core/workflow/temporal_adapter.py` 是唯一现成 Temporal 适配点）。
- **幂等键（用 Temporal 天然去重）**：schedule 触发的 workflow id 设为 `f"balance-refresh-{window}"`，其中 `window` 是按刷新周期对齐的时间窗（如 `YYYYMMDDHH` 或 5 分钟桶）。**同窗口同 workflow id → Temporal 拒绝重复启动（`WorkflowExecutionAlreadyStarted`）**，无需自己写去重表。快照落库时另以 `ProviderBalanceSnapshot.checked_at` 落在同窗口的记录做二次幂等（避免手动 refresh 与定时在同窗口重复写）。
- **跨进程互斥（不能用进程内 lock）**：手动 `RefreshProviderBalancesRequest` 与定时任务的互斥，落在**数据库层**——用 Postgres **advisory lock**（`pg_try_advisory_lock(key)`，key 按 `account_group` 或全局 balance-refresh 取哈希）或对快照表的行级锁串行化；拿不到锁即跳过本次（定时）或排队/拒绝（手动）。**禁用 asyncio.Lock / 进程内单例**——多 worker 下无效。最稳是让定时刷新只由**单一 Temporal workflow 串行执行**（同一 workflow id 串行 activity），手动 refresh 也路由进同一 workflow 队列，从源头消除并发。
- **5 QPS/账户限流（不能只靠「别并发」约定）**：在 poller 调用层（`packages/ops/balance/service.py` 或新 refresh activity 内）做**令牌桶/信号量按 `account_group` 限速**，确保对火山/阿里同一账户的请求 ≤5 QPS。多 account_group 之间可并发，单 account_group 内串行+限速。
- 快照落 `ProviderBalanceSnapshot`（契约第 212 行已就绪）。新增 balance-refresh workflow + schedule 定义放 `apps/worker/` + `deploy/`。

### 2.7 平台总览大盘

`apps/web` 新增大盘，**只展示收窄后的 5 个余额账户 + 6 个能力的花销**。前端经 `realData.ts` 过滤（参照已有 sandbox/demo 过滤模式），不展示已排除的 minimax/deepseek/kimi/巨量。**余额按 `account_group` 折叠成一行；花销按能力逐项展示、不折叠**（§1.6 / §5.2）。

---

## 3. 数据契约 / 迁移

**契约改动**（`packages/core/contracts/providers.py`）：
- `ProviderPriceItem.unit` Literal 追加 `"provider_credit"`（§2.1）。
- 新增 `ProviderBillingConfig` + 其 create/patch request（§2.4）。
- 同步 `packages/core/contracts/__init__.py` 的 import + `__all__`（CLAUDE.md 硬性要求，否则下游 import 失败）。

**ops 契约**（`packages/core/contracts/ops.py`）：低余额告警 code（`balance.low`）、`ProviderBillingConfig` 若归 ops 域则放这里。

**迁移**（`packages/core/storage/alembic/versions/`）：当前 head 是 `0020_selection_reservation_active_slot.py`（注意 `0018` 有两个文件，落地前 `alembic heads` 确认实际单一 head）。新增 **`0021_provider_billing_config.py`**（接 0020 后，单一线性链）：建 `provider_billing_config` 表 + `provider_balance_snapshot` 表（若 §2.6 要持久化快照）。

**重生成 OpenAPI（contract-first 硬性）**：
```bash
python scripts/export_openapi.py && (cd apps/web && npm run generate:api)
```
改了 `ProviderPriceItem.unit` 和新增契约/端点必须重生成 `apps/web/src/api/openapi.json` + `schema.d.ts`（CI 校验漂移；`schema.d.ts` 禁手改）。
**注意 OpenAPI 漂移是 env 敏感的**（key-order 随本地 pydantic/Python 版本变）——若 CI 的 unit check 绿、本地却报 drift，那是本地假阳性，**别本地 regen「修」它**。

---

## 4. 分期（每期改动文件 + 验证）

### P0（不依赖火山真凭据，立即可做且可独立验证）

**目标**：火山 TTS 合成接入 + minimax 音色链路决策（默认方案 A）+ 花销修复 + actual_cost + 告警 + 大盘。

改动文件：
- `packages/ai/providers/volcengine_tts.py`（新增，合成）；`packages/ai/providers/minimax.py`（方案 A 保留供音色 / 方案 B 删）；`packages/ai/providers/__init__.py`（合成默认插件指向 volcengine）
- `packages/ai/netpolicy.py`（加 openspeech/ark/open.volcengineapi.com；删 deepseek/moonshot；minimax host 视音色决策保留或删）
- `packages/ai/gateway/provider_gateway.py`（`_estimated_cost_from_usage` 加 `provider_credit` 分支）
- `packages/core/contracts/providers.py` + `__init__.py`（unit 加 provider_credit）
- `packages/core/storage/provider_seed.py`（按 §1.4：新增 volcengine.tts profile/secret_ref/concurrency_key/catalog/price item；heygem/openai.image 加 provider_credit 价目；minimax 四处按 A/B 处理）
- `packages/ops/balance/registry.py`（删 deepseek/kimi/minimax 三 import + 三实例化 + 过时 docstring；不加 volcengine——poller 属 P1）
- `packages/ops/balance/providers/deepseek.py`、`kimi.py`、`minimax.py`（删文件；minimax balance poller 无论 A/B 都删）
- `packages/ops/alert_rules.py`（新增，低余额规则）
- `apps/api/services/voices.py`（方案 B 且火山无音色接口时才动：清理 sync 分支）
- `apps/web`（大盘 + realData.ts 过滤）

验证：
```bash
python -m pytest -q tests/providers tests/contract/test_provider_*    # TTS 合成插件 + unit 契约
python scripts/export_openapi.py && (cd apps/web && npm run generate:api)
scripts/ci_gate.sh    # 完整门禁（需 PG 55432 + Temporal 7233 + MinIO）
```
**重启 worker**（TTS 换型影响音频节点）。**方案 A 下额外手测**：在「设置」里以保留的 minimax profile 跑一次「同步账户音色」，确认 `sync_voices` 仍工作（防音色链路回归）。

### P1（接火山/阿里真凭据）

**目标**：火山余额 poller + dashscope BSS + Temporal 定时刷新。

改动文件：
- `packages/ops/balance/providers/volcengine.py`（新增）、`packages/ops/balance/registry.py`（加 `VolcenginePoller` import + 实例化）
- `pyproject.toml`（可选 extra：volcengine-python-sdk + alibabacloud_bss_open_api）
- `apps/worker/` + `deploy/`（balance-refresh workflow + schedule；幂等=workflow id `balance-refresh-{window}`；互斥=PG advisory lock / 单 workflow 串行；限流=按 account_group 令牌桶 ≤5 QPS）
- `packages/core/storage/alembic/versions/0021_*.py`（provider_balance_snapshot 表）

验证：
```bash
# 装 extra 后真凭据冒烟
python -m pytest -q tests/integration/test_sqlalchemy_providers.py
scripts/ci_gate.sh
```
**P1 验收门（硬性，防摘标走过场）**：火山余额冒烟脚本必须**真凭据跑通且真正断言实时性**——
1. 调 `QueryBalanceAcct` 记录余额 `B0`；
2. 触发一次真实计费消费（一次 TTS 合成或一次 Seedance 生成）；
3. 等待数秒后再调 `QueryBalanceAcct` 取 `B1`，**断言 `B1` 相对 `B0` 发生预期变化（或在文档承诺的延迟窗内变化）**；
4. 只有该断言通过，才把 poller `detail` 与文档/PR 里的「待真凭据冒烟验证」摘掉，并据实记录实时性口径（实时 / T+N 延迟）。
- 若断言显示余额**非实时**（如 T+1），则**不摘「实时」相关措辞**，改标真实口径，UI 同步如实展示。

### P2（对账 + 单位归一）

**目标**：火山账单 API 对账 + Seedance 单位从 media_second 归一到 token。

改动文件：
- `packages/ops/`（reconcile 写回 actual_cost，调火山 `ListBillOverviewByProd`/`ListBillDetail`）
- Seedance 插件 + provider_seed：把 `unit="media_second"`/`video_seconds=15` 改成 `token` 口径（透传 `usage.total_tokens`）
- `packages/core/contracts/providers.py`（若 ReconcileBilling 需补字段）

验证：先在真实火山账户跑一次 `ListBillOverviewByProd` 看实际 Product 取值（**实测，medium 置信度**），确认 TTS vs Seedance 能否拆，再写对账逻辑。

---

## 5. 风险与坑

1. **火山签名/SDK 依赖**：优先 `volcenginesdkbilling` 走 SDK 免手写 V4 签名（HMAC-SHA256）；SDK 进可选 extra，未装降级 unsupported（照搬 aliyun_bss 范式，不崩）。
2. **账户级余额不能按能力拆**：火山/阿里/openai 余额都是账户级总额。「每个平台余额」能做到平台级真实，「每个能力余额」火山阿里都给不了——按能力归因只能靠本地逐次 ledger 的花销侧。**UI 折叠规则：余额按 account_group 折叠成一行，花销按能力逐项不折叠**——别把 dashscope/volcengine 的 per-capability 花销折没。
3. **账单 T+1 延迟 ≠ 实时余额**：火山账单账期粒度只到月，当月数据 T+1 增量、月汇总建议次月第 4 自然日 10 点后拉。**当日实时花销只有本地估算，真值 T+1**。别把账单 API 当实时花销监控用。
4. **TTS 换型 + 音色链路双坑**：(a) 改插件后只重启 API 不生效，**必须重启 worker**（`packages/production/pipeline/nodes/tts.py` 上游）；(b) **minimax 换型会静默拖掉 voice-sync/clone/preview**（§1.3），P0 必须按方案 A/B 显式处理，不能只换合成。
5. **密钥进 SecretStore**：火山三套 secret（openspeech appid/token、Ark API key、billing AK/SK）各自进 `SecretStore`/`ProviderProfile`，绝不进 env/代码。provider_seed 只 seed `secret_ref`，**不 seed 密钥值**（现有 seed 注释已强调，沿用）。
6. **OpenAPI 漂移 env 敏感**：CI 的 pinned venv 是事实源；本地 regen 出的 drift 若 CI unit check 绿即本地假阳性，别本地 regen「修」。
7. **火山 unknown 项诚实标注（硬性）**：`QueryBalanceAcct` 实时性口径未经官方承诺、TTS/Seedance 的 Product 取值未实测——方案与代码 `detail` 一律标 **「待真凭据冒烟验证」**。**冒烟脚本必须真正断言实时性（§4 P1 验收门），通过前不摘标、不宣称「实时」**；否则摘标沦为走过场。
8. **5 QPS/账户限制 + 互斥落点**：火山账单/余额 API 5 QPS/账户。Temporal schedule 定时刷新与手动 refresh 的互斥**必须落 DB 层（advisory lock）或单 workflow 串行**，**禁用进程内 asyncio lock（多 worker 失效）**；限流用按 account_group 令牌桶，不靠「别并发」约定（§2.6）。
9. **registry 清理别留悬空 import**：`build_pollers()` 删 deepseek/kimi/minimax 时，**import 行与实例化一起删**（registry 第 24-26 行三 import + build_pollers 三实例化），并删过时 docstring；确认 `tests/` 无断言这三个 poller 存在的用例。**保留 `openai_relay.py`**（openai.image 镜像余额要用），别误删。

---

**相关真实文件路径汇总**（均为绝对路径，已逐条核实）：
- 成本链 bug：`/Users/yoryon/Projects/cutagent-genesis/packages/ai/gateway/provider_gateway.py`（`_estimated_cost_from_usage` 第 424-439 行；`provider_credits` 字段第 312 行存）
- 价目/余额契约：`/Users/yoryon/Projects/cutagent-genesis/packages/core/contracts/providers.py`（`ProviderPriceItem.unit` 第 150 行；`provider_credits` 第 31 行；`ProviderInvocation.actual_cost` 第 53 行；`billing_status` Literal 第 47 行；`ProviderBalanceItem.account_group` 第 193 行；`ReconcileBilling*` 第 223-245 行；`ProviderBalanceSnapshot` 第 212 行）
- minimax ai 插件（含音色 voice_list/clone/design/preview）：`/Users/yoryon/Projects/cutagent-genesis/packages/ai/providers/minimax.py`（`_voice_list` 第 54、`_clone` 第 203、`_design` 第 237、`_preview_voice` 第 331 行）
- voice-sync 链路：`/Users/yoryon/Projects/cutagent-genesis/apps/api/services/voices.py`（`sync_voices` / `_select_tts_profile_for_sync`，调 `tts.speech` 的 `voice_list` operation）
- balance poller 模板 + 注册：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/providers/aliyun_bss.py`（prefixes 含 dashscope，仿写火山）、`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/registry.py`（第 24-26 行三 import、build_pollers 第 31-38 行）、`base.py`、`service.py`
- 待删/保留的 balance poller 文件：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/balance/providers/{deepseek.py,kimi.py,minimax.py}`（删）、`{openai_relay.py,heygem.py,aliyun_bss.py}`（保留）
- seed：`/Users/yoryon/Projects/cutagent-genesis/packages/core/storage/provider_seed.py`（minimax 四处：profile id/provider_id 第 32-33、secret_ref 第 38、concurrency_key 第 39、catalog `price_minimax_prod` 第 228、price item `price_minimax_tts_chars` 第 241-244 行）
- netpolicy：`/Users/yoryon/Projects/cutagent-genesis/packages/ai/netpolicy.py`（`DEFAULT_ALLOWED_HOSTS` 第 37-47 行，三 host 第 45 行附近）
- 预算告警基座：`/Users/yoryon/Projects/cutagent-genesis/packages/ops/budget_evaluation.py`
- Temporal 适配点：`/Users/yoryon/Projects/cutagent-genesis/packages/core/workflow/temporal_adapter.py`
- Seedance 计划：`/Users/yoryon/Projects/cutagent-genesis/docs/2026-06-22-seedance-t2v-thin-slice-plan.md`（计费段需从 media_second 改 token）
- 迁移目录：`/Users/yoryon/Projects/cutagent-genesis/packages/core/storage/alembic/versions/`（当前 head `0020_selection_reservation_active_slot.py`，新增接 `0021_`）