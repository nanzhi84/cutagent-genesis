# M6N 施工简报：S3ObjectStore 健壮传输（multipart 上传 + 超时/重试调优）

负责：Codex（执行）/ Claude（架构 + 验收）
分支：`feat/m6n-robust-oss-transfer`
来源：M6M 验收时，演示切远端阿里云 OSS（上海）后，strict 真对齐 run 的渲染阶段卡死——视频产物（portrait_track/rendered/final，各约 10–20MB）用单发 `put_object` 传上海慢/失败，Temporal 重试也不过，成片出不来。strict 真对齐**能力已证**（真 ASR、source=asr、真词级时间戳），差的是把大视频产物**可靠快速**地传上远端 OSS。原仓库正是用 multipart（`OSS_MULTIPART_THRESHOLD_MB`/`OSS_MULTIPART_PART_SIZE_MB`/`OSS_MULTIPART_THREADS`/`OSS_UPLOAD_RETRIES`）解决同一问题。

## 已验证事实（勿推翻）

- 远端 OSS（videoretalk-test-bucket@oss-cn-shanghai，addressing=virtual，checksum when_required）下：小文件（TTS mp3 175KB）`put_object` 秒传；**大视频文件单发 put_object 不可靠**（render 节点卡住/重试耗尽，无 video 产物）。
- genesis `S3ObjectStore.put_bytes` 当前是 `self._client.put_object(Bucket,Key,Body=content)` 单发；`get_bytes` 是 `get_object`+`body.read()` 单发。
- botocore `Config` 当前无显式 connect/read 超时（默认各 60s）、无显式 retries。

## 改动清单（仅 `packages/core/storage/object_store.py` + 测试 + 文档）

### A. put_bytes 改 multipart 托管传输

- A1 `S3ObjectStore.put_bytes`：保留 `sha256=hashlib.sha256(content).hexdigest()` 与本地 cache 写入语义不变；上传改用 boto3 托管传输：
  `self._client.upload_fileobj(io.BytesIO(content), ref.bucket, ref.key, Config=self._transfer_config)`，
  其中 `self._transfer_config = boto3.s3.transfer.TransferConfig(multipart_threshold=…, multipart_chunksize=…, max_concurrency=…, use_threads=True)`。
  小于阈值的文件 upload_fileobj 会自动单发，大文件自动分片并发——对 MinIO 与 OSS 都适用。
- A2 返回的 `StoredObject(ref, size_bytes=len(content), sha256=…)` 不变（size/sha256 用内存 content 计算，不依赖远端）。

### B. 下载也健壮（可选但建议）

- B1 `get_bytes`：大对象用 `download_fileobj(bucket,key,buf,Config=self._transfer_config)` 写入 BytesIO 再返回 bytes（render 节点 cache miss 时从 OSS 取输入也会大）。保持现有 close 语义/异常不变；失败仍抛原异常。

### C. botocore Config 超时/重试

- C1 `_build_client` 的 `Config` 增：`connect_timeout`、`read_timeout`、`retries={"max_attempts": N, "mode": "standard"}`（保留既有 signature_version=s3v4 + addressing_style + checksum when_required）。`client_factory` 分支同样传入。
- C2 这些值 + TransferConfig 参数都从 env 读，给安全默认（建议：threshold 8MB、chunk 8MB、concurrency 4、connect 10s、read 120s、max_attempts 5）：
  - `CUTAGENT_OBJECTSTORE_MULTIPART_THRESHOLD_MB`、`_MULTIPART_CHUNK_MB`、`_MAX_CONCURRENCY`、`_CONNECT_TIMEOUT`、`_READ_TIMEOUT`、`_MAX_ATTEMPTS`。
- C3 `S3ObjectStore.__init__` 增对应参数（带默认），`object_store_from_env()` 读 env 传入。不破坏 M6M 的 addressing_style 参数与现有签名顺序（新参数都给默认值，加在末尾）。

### D. 测试 + 文档

- D1 单测：用注入的 fake client/transfer 断言 put_bytes 走 upload_fileobj + TransferConfig 参数透传；object_store_from_env 读新 env。sha256/size 返回不变。不连真 OSS。
- D2 既有 object store backend 测试不回退（MinIO 路径仍 put/get/presign）。全量基线（约 187 单测）不回退。
- D3 `docs/ops/objectstore-oss.md` 补 multipart/超时 env 段；说明远端 OSS 出片靠 multipart 才实用。

## 边界（Out of scope）

- 不改 provider 插件、不改 pipeline、不碰前端。
- 不做 OSS 生命周期/GC、不做 ContentType 推断（M6f 范畴）。
- 真口播片（HeyGem）单列。

## Verification（sandbox 内 Codex 自验）

- 全量 pytest（约 187）+ 新测全绿，所有 pytest 包 `timeout -k 5 600`，用主仓 venv。MinIO backend 路径单测不回退。

## 验收门（验收官，真 OSS live）

1. 演示切 OSS 后端（addressing=virtual）+ 本批 multipart 配置，提交 `strict_timestamps=true` 真人声 run：render 各节点的大视频产物**可靠传上 OSS**，PortraitTrackBuild→Render→Subtitle→Export 全过，**完整 strict 真对齐成片产出**；下载抽帧 + ASS 时间与真 ASR 对齐一致。
2. MinIO 后端回归不变（addressing=path 默认仍 put/get/presigned）。
3. 全量 + DB + Temporal 三套绿。
