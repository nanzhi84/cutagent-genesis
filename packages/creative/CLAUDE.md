# packages/creative

Case 领域：自进化闭环算法、指标导入匹配、Case/学习的 DB 落库，以及 URL 参考视频抽取。**既有纯逻辑（评分/特征/评分卡升级）也有持久化层。** 被 `apps/api/services/case_agent.py`、`apps/api/routers/{creative,case_agent}.py` 调用。

## 职责
- 自进化纯算法：`cases/evolution.py`（指标评分/特征抽取）+ `cases/rubric.py`（case_rubric_v1 评分卡、盲预测、复盘、升版）。
- 指标导入匹配：`cases/metrics_import.py`（§25.4 / §25.1）—— `match_metrics_rows`（按 matching policy 把导入行匹配到 publish record）、`observation_contract_from_match`。
- DB 落库：`cases/sqlalchemy_learning.py`（脚本草稿 / 采用 / active hard-memory 读取）、`cases/sqlalchemy_repository.py`（Case CRUD + 派生计数）、`cases/sqlalchemy_rubric.py`（评分卡 / 预测 / 奖励 / 升版）。
- 参考抽取：`reference_extract.py`（yt-dlp 取信息+字幕，`source`=subtitle/asr，含抖音 `_DouyinExtract` 兜底）、`reference_cookies.py`（header/netscape/json 三格式 cookie 解析 + SecretStore 持久化）。

## 约定与要求
- contract-first：I/O 走 `packages.core.contracts`。
- 自进化算法（`evolution.py`）为纯函数：评分/特征抽取不查 DB、不调 provider，便于测试。
- `CaseMemory` 仅保留为用户手钉硬约束/品牌红线；自动学习走 `CaseRubric` / `RewardSignal` / `ScorePrediction`，不再走逐条记忆提案审批。
- cookie auto-refresh（Playwright）刻意不实现：`refresh_status()` 恒返回 `auto_refresh_supported=False`，对应 `/api/creative/reference-extractor/refresh-cookies` 返回 410；运营手动粘贴 cookie。

## 测试
- `pytest tests/creative`（`test_reference_extract.py` / `test_reference_cookies.py` / `test_case_evolution_logic.py`，覆盖参考抽取、cookie、自进化纯逻辑与指标匹配）；SQLAlchemy 落库另见 `tests/integration/test_sqlalchemy_case_learning.py`。

## 注意 / 坑
- 指标**匹配策略**（`match_metrics_rows`）在本包 `cases/metrics_import.py`；指标行的 DB 写入/落库在 `packages/production` 仓储，别混淆两者。
- 改 `packages/core/contracts` 后须按根 CLAUDE.md 重新生成 openapi.json + schema.d.ts。
