# 仓库质量门禁

通用 CI 的 Interface 是 `.github/workflows/backend-quality.yml`。它把格式、静态分析、
关键类型、契约、迁移、Registry、浏览器认证/入口安全、RAG 基线、覆盖率和依赖审计集中在同一个
治理 Module，让本地与 CI 共享相同命令，并把失败知识保持在一个 Seam 上。

## 本地验证

先安装锁定依赖：

```bash
uv sync --dev --locked
```

依次运行：

```bash
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync python scripts/generate_contract_types.py --check
uv run --no-sync python scripts/generate_rag_eval_schemas.py --check
uv run --no-sync python -m backend.tools.registry_cli validate
uv run --no-sync pytest -q \
  tests/test_migrations.py \
  tests/test_document_catalog_migration.py \
  tests/test_indexing_worker_migration.py
uv run --no-sync pytest -q \
  --cov=backend \
  --cov=scripts \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=80
```

修改浏览器认证、Cookie、Rate Limit 或安全响应头时，应先运行聚焦回归，再运行上面的完整覆盖率
门禁：

```bash
uv run --no-sync pytest -q \
  tests/test_auth_routes.py \
  tests/test_auth_http.py \
  tests/test_auth_token_lifecycle.py \
  tests/test_auth_cleanup.py \
  tests/test_auth_rate_limit.py \
  tests/test_rate_limits.py \
  tests/test_rate_limit_http.py \
  tests/test_rate_limit_runtime.py \
  tests/test_rate_limit_app_integration.py \
  tests/test_security_headers.py \
  tests/test_settings_security.py
```

这些测试必须证明 Access Token 不经 Cookie 持久化、Refresh Token 不进入 JSON、HttpOnly
`Path=/auth` Cookie 的 rotation/replay detection、User→RefreshToken 锁序、自然过期后的 ledger
forensic retention/purge、expired-before-revoked 判定避免旧 token DoS、当前设备与全部设备撤销、
unsafe auth POST metadata 在 Rate Limit 前拒绝、
chunked body 在计费后受 16 KiB streaming cap 约束、`/auth` 成功/401/429 no-store、typed 429/503、
登录/注册 username 二级限流早于同步密码 handler，以及 CSP 只应用于正式前端 HTML且全局
`X-Frame-Options: DENY`。

Middleware 顺序的回归锚点是
`test_cross_site_auth_form_is_rejected_before_rate_limit_consumption` 与
`test_chunked_body_consumes_host_quota_before_streaming_cap_returns_413`：前者锁定恶意 metadata
不消耗 quota，后者锁定无/伪 Content-Length stream 必须先计费再读取，避免文档或重构把两层
16 KiB 防护误写成同一位置。

前端门禁还应覆盖 Access Token 不写 `localStorage`、页面 refresh 恢复、同标签 single-flight、
Web Locks 跨标签串行、等待锁后的 generation/tombstone 重检、refresh username 主体一致、旧 401
不跨账号重试、原请求最多重试一次，以及 Run/SSE 只读取内存认证状态。

PostgreSQL 多实例锁序不能只靠 SQLite 证明；有专用临时库时额外运行：

```bash
AUTH_POSTGRES_TEST_URL=<专用 PostgreSQL DSN> \
  uv run --no-sync pytest -q tests/test_auth_postgres_integration.py
```

SQLite 测试覆盖迁移中的数据转换与升级链。Document Version identity 收敛迁移不可逆，发布门禁
必须验证 `upgrade head` 成功，并验证 downgrade 明确 fail-closed。PostgreSQL smoke 应连接专用
临时数据库，不能指向共享或生产数据库：

```bash
# 先通过本地 Secret 管理器为当前进程注入专用临时库的 DATABASE_URL。
uv run --no-sync alembic upgrade head
uv run --no-sync python -c "from backend.infra.database import assert_schema_current; assert_schema_current()"
```

RAG 基线必须能从受控 observations 原样重建：

```bash
uv run --no-sync python scripts/evaluate_rag.py score \
  --dataset evals/rag/rag_smoke_v1.json \
  --observations evals/rag/offline_smoke_observations_v1.json \
  --gates evals/rag/gates_v1.json \
  --report /tmp/rebuilt-rag-baseline.json \
  --fail-on-regression
cmp /tmp/rebuilt-rag-baseline.json evals/rag/baseline_v1.json
```

非模型 Runtime 开销使用固定 fake Adapter 与 ASGI transport 建立可复现基线，避免把真实模型
和外部网络波动混入仓库门禁：

```bash
uv run --no-sync python -m scripts.benchmark_runtime \
  --check \
  --report /tmp/runtime-benchmark.json
```

该 profile 门禁 Thread HTTP 顺序/并发 p95、Event 首次持久投影开销、SSE 编码与本地取消信号；
真实模型 TTFT、总延迟和 tokens/s 仍必须在固定模型、Document Version 与硬件 profile 下单独
记录，不能用本基线冒充端到端 SLO。

普通单元测试必须使用 fake model，不能在 CI 中隐式下载大型 Embedding 模型。升级
`sentence-transformers`、`transformers`、`torch`、Embedding 模型或模型 revision 时，发布人
必须在已经预热模型缓存的隔离环境中额外执行真实离线 smoke：

```bash
EMBEDDING_MODEL_REVISION=5617a9f61b028005a4858fdac845db406aefb181 \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run --no-sync python scripts/smoke_embedding.py
```

该 smoke 强制使用 40 位不可变模型 revision，同时调用 query/document 编码 Interface，校验
向量维度、有限值与单位范数，并输出 Torch、Transformers 与 Sentence Transformers 版本；
模型缓存缺失时应直接失败，不能临时放开联网来掩盖发布环境缺包。升级模型时必须先评审并
同步替换配置与命令中的 commit SHA。

依赖审计需要访问 PyPI 漏洞数据库；CI 会从 `uv.lock` 导出生产依赖，不审计未锁定的
临时解析结果：

```bash
uv export --frozen --no-dev --no-emit-project \
  --format requirements-txt --output-file /tmp/requirements.txt
uv run --no-sync pip-audit \
  --requirement /tmp/requirements.txt \
  --disable-pip --strict --progress-spinner off
```

## 门禁范围

- `ruff format --check` 覆盖仓库内全部 Python 文件，在 CI 中为非阻断检查：保留检查日志，
  失败不阻断后续步骤，也不单独导致工作流失败。其他门禁仍保持阻断；本地命令仍返回非零
  退出码，可运行 `uv run --no-sync ruff format .` 修复格式。
- `ruff check` 除基础错误外，显式阻断 async 函数中已知的同步 HTTP 调用、阻塞进程
  调用、内建文件打开和 `time.sleep`。这是针对明确调用形状的静态门禁，不会推断任意
  同步调用链，也不能自动识别同步 SQLAlchemy、第三方 SDK 或 CPU 密集工作。
- `/auth/register` 与 `/auth/login` 使用同步 SQLAlchemy 和 PBKDF2，因此保留为同步
  route，让 FastAPI 在线程池执行整个 handler；`tests/test_auth_routes.py` 锁定该执行
  形态，补足 Ruff 无法推断的部分。所有 auth unsafe POST 必须先通过来源、login/register JSON
  media type、Content-Length 语法与声明的 16 KiB 上限；该 metadata guard 位于 Rate Limit 外层，
  拒绝请求不能消耗受害者 quota。Rate Limit 计费后由内层 body guard 流式累计实际 body，阻止
  无/伪 Content-Length 超过 16 KiB，仍早于 route/PBKDF2/token mutation。随后 login/register
  必须完成直接 client IP 与
  `IP + NFKC/trim/casefold username` 两次 Rate Limit check；复合 bucket 每次消耗两个 quota
  unit，任一拒绝或存储异常都不得执行 PBKDF2。
- Rate Limit 只使用 ASGI `scope.client`。Nginx、Ingress 或 LB 前置时，发布检查必须确认只有可信
  代理可写 forwarded headers，且 ProxyHeaders allowlist 已在 Rate Limit Middleware 之前修正
  client；禁止在 Module 内直接解析任意 `X-Forwarded-For`。
- 有效 Bearer 只解析为稳定 access subject，raw access/refresh token 不作为 quota identity；
  refresh/当前设备 logout 使用 host 粗限额 120/min，logout-all 使用 subject。除明确静态/健康/
  Docs/preflight skip 外，未知与未来动态 path 必须默认进入 general policy。
- mypy 先覆盖 Run/Event、Guardrail/Sandbox、Schema、工具契约与安全策略等关键
  Interface；新增或修改这些 Module 时不得用全局 ignore 绕过。
- pytest 覆盖率以 `backend` 与 `scripts` 的 statement coverage 计算，初始下限为 80%；
  当前不采集 branch coverage；待建立可复现报告并补齐关键低覆盖 Adapter 后再设门禁。
- 契约生成、Registry、离线 RAG 基线和 SQLite 迁移测试不依赖真实模型、Redis、
  Milvus 或 MinIO。生产 Alembic smoke 明确依赖 CI 的 PostgreSQL 15 Adapter，避免只在
  SQLite 方言上验证发布迁移。
- `storage-compatibility` job 先将六个必填变量逐项 unset 和置空，证明生产 Compose
  对缺失或空 Secret 都 fail-closed；随后使用生产 Redis、Milvus、etcd 与 MinIO 镜像，
  在 `/tmp` 隔离卷上执行
  Redis Streams/跨实例取消、真实 Redis Rate Limit、版本化 schema、租户与版本过滤、
  Dense/BM25 Hybrid 检索和版本删除。这条门禁同时覆盖客户端/服务端协议、healthcheck 与凭据
  变量名。它只安装锁定的 `storage-compatibility` 依赖组，不下载与本 job 无关的
  Torch/CUDA/Embedding 栈。

真实 Redis Rate Limit smoke 使用认证 `REDIS_URL` 和至少两个独立 Adapter，必须验证：同一
identity 在固定 window 达限后得到 429、不同 identity 隔离、Redis `TIME` 驱动的 window 能
reset、跨 Adapter 共享计数、Redis key 不包含 raw IP/username/Bearer/Refresh Token，以及 Redis
不可用时返回 typed 503 而不是放行。CI 通过以下兼容 smoke 执行该证据：

```bash
uv run --no-sync python -m scripts.smoke_redis_compat
```

内存或 fake Adapter 单测只能证明 Module contract，不能替代真实 Redis Lua、时钟、TTL 与多连接
共享行为。

## 生产入口安全配置

生产启动校验必须同时满足：

```text
AUTH_REFRESH_COOKIE_SECURE=true
AUTH_REFRESH_LEDGER_RETENTION_DAYS=30
RATE_LIMIT_ENABLED=true
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_HMAC_KEY=<至少 32 字符的稳定随机 Secret>
```

`RATE_LIMIT_HMAC_KEY` 必须与 `JWT_SECRET_KEY` 分离；二者相同会阻止生产启动。Rate Limit Redis
Adapter 使用认证 `REDIS_URL`，`RATE_LIMIT_KEY_PREFIX` 只允许稳定的短标识符。开发/测试可以
使用 `RATE_LIMIT_BACKEND=memory`；key 留空时仅生成进程内临时 HMAC key，不提供跨重启或多实例
配额事实。

Refresh Cookie 固定 HttpOnly 与 `Path=/auth`；`SameSite=None` 必须同时启用 Secure。same-origin
auth 始终可信；跨 origin 只有在 `CORS_ALLOW_CREDENTIALS=true` 且命中明确 allowlist 时可信，
空 allowlist 表示 same-origin-only，禁止 `*`。Vite 本地默认端口是 3000；生产 same-origin-only
可留空，跨 origin 前端必须替换为真实 HTTPS origin。

`ADMIN_INVITE_CODE` 留空即禁用公开 admin 注册；启用时必须与 JWT/Rate Limit Secret 分离。
所有 HTTP 响应都校验 `Referrer-Policy: no-referrer`、
`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY` 与受限 `Permissions-Policy`；
Content-Security-Policy 只校验正式前端 HTML，FastAPI `/docs`、`/redoc` 与 JSON 响应不得附加
CSP，以免把 API 文档兼容性和前端策略耦合。

Refresh ledger 的保留与有界 purge 是独立运维职责，不在 API 热路径执行。发布必须为以下命令
配置 scheduler、失败重试与告警：

```bash
uv run --no-sync python -m backend.auth.cleanup
```

默认 `--batch-size=1000`、`--max-batches=100`，无 dry-run；只删除
`expires_at + AUTH_REFRESH_LEDGER_RETENTION_DAYS` 已越过的行。retention 只保留 forensic/audit
evidence；服务端先判 expired，过期行不能触发用户级 replay 撤销。完整操作说明见
`docs/runbooks/auth-token-lifecycle.md`。

## 开发 Compose 对象存储排障

开发 `docker-compose.yml` 使用 RustFS。在仓库根目录的 `.env` 或进程环境中设置
`RUSTFS_ACCESS_KEY` 与 `RUSTFS_SECRET_KEY`，Compose 将其同时传给 RustFS、桶初始化
服务及 Milvus 的 `MINIO_ACCESS_KEY_ID` / `MINIO_SECRET_ACCESS_KEY`。不得把真实值写入
仓库或诊断日志。初始化服务创建 Milvus 默认使用的 `a-bucket`；已有数据时不要随意修改
桶名、`rootPath` 或删除卷。

在仓库根目录运行以下命令核对配置和启动状态：

```bash
docker compose config --quiet
docker compose up -d
docker compose ps -a
docker compose logs --tail 100 standalone create-bucket
```

期望 `standalone` 为 `healthy`，`create-bucket` 为 `Exited (0)`。如果 Milvus 日志出现
`failed to check blob bucket exist` 和 `Access Denied`，先检查 Milvus 是否收到上述两个
凭据变量且与 RustFS 一致，再检查桶名；延长健康检查等待时间不能解决认证失败。
修改 Compose 的环境变量后需用 `docker compose up -d` 重建对应容器，单纯 `restart`
不会应用新环境变量。RustFS 健康而 Milvus 失败时，不应通过清空数据卷处理。

## 远程嵌入 API

远程模式复用同一个 EmbeddingRuntime、query/document Interface、ProviderExecutor、并发 gate、
批处理和隔离缓存，不加载本地模型，也不在失败时降级成本地模型。在根目录 `.env` 显式配置：

```dotenv
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_BASE_URL=https://your-embedding-api.example/v1
EMBEDDING_API_KEY=<服务端密钥>
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_MODEL_REVISION=provider-managed-v1
DENSE_EMBEDDING_DIM=1024
EMBEDDING_WARMUP_ON_START=true
EMBEDDING_TIMEOUT_SECONDS=30
```

基址必须为无 userinfo、query、fragment 的 HTTPS URL，应用会追加 `/embeddings`；模型需要
支持字符串数组输入和 `encoding_format=float`。不会自动复用 `BASE_URL` / `ARK_API_KEY`，
如使用同一服务，需将它们的值分别填入上述两个专用字段。密钥只保存在服务端环境中。

查询和文档使用同一模型，按响应 `index` 恢复顺序，校验数量、维度与有限数值后进行 L2
归一化。HTTP 不跟随重定向，只有 ProviderExecutor 负责重试；所有等待者取消或超时后，
对应批次的在途 HTTP 会被取消。正常关闭也会释放 client 和批处理任务。

`EMBEDDING_MODEL_REVISION` 在远程模式是运维部署标签，不会作为 API 参数，也不保证服务商
固定权重。服务商切换模型版本时需更新此标签并重新构建文档索引。索引身份包含 provider、
基址的哈希、模型、部署标签、维度和归一化方式；不含 Key。与本地模式切换时同样需要重建
已有文档索引，不可混用旧向量。

停止并重启 API 与两个 worker（仓库根目录 PowerShell）：

```powershell
Remove-Item Env:EMBEDDING_WARMUP_ON_START -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m backend.launcher --port 8000
```

预热会真实调用远程服务，消耗服务商额度。模型可用且其他依赖正常时 `/health/ready` 返回
200，`provider_runtime.embedding.ready=true`；远程模式的 `model_loaded=false` 表示未加载
本地权重，不影响就绪判定。无需设置 `HF_ENDPOINT` 或下载模型；这些只影响本地模式。

离线回归使用 MockTransport，不发送真实文本或 Secret：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_remote_embedding.py tests/test_embedding_runtime.py
```

## 开发环境模型下载排障

本地 Embedding 默认使用固定 revision 的 `BAAI/bge-m3`。API 与两个 worker 都会在
`EMBEDDING_WARMUP_ON_START=true` 时加载模型。首次下载应单独完成，避免把网络下载放进
Provider 的启动预热 deadline。

如果出现 `FileMetadataError: Distant resource does not seem to be on huggingface.co`，
检查 `HF_ENDPOINT`。Hub 客户端需要模型响应中的 commit、ETag 和文件大小；镜像返回跨域
重定向而未提供这些元数据时，浏览器能打开链接也不代表客户端能下载。使用可访问且保留
Hub 元数据的源，例如 `.env` 中的 `HF_ENDPOINT=https://huggingface.co`。不关闭 TLS 校验，
也不通过修改已安装依赖跳过元数据校验。

仅需联调页面和普通 API 时，在本地 `.env` 中设置 `EMBEDDING_WARMUP_ON_START=false`
并重启。`/health/live` 应返回 200；未加载模型时 `/health/ready` 仍返回 503，RAG 与
文档入库仍依赖模型可用。

以下 PowerShell 命令从仓库根目录运行，为 `.env.example` 中的默认模型和 revision
准备 Sentence Transformers 所需文件（约 2.29 GB，不下载 ONNX、图片或其他权重）。
如果更改了模型或 revision，需同步命令并核对该模型要求的文件：

```powershell
$env:HF_ENDPOINT="https://huggingface.co"
.\.venv\Scripts\hf.exe download BAAI/bge-m3 `
  config.json config_sentence_transformers.json modules.json sentence_bert_config.json `
  1_Pooling/config.json tokenizer.json tokenizer_config.json special_tokens_map.json `
  sentencepiece.bpe.model pytorch_model.bin `
  --revision 5617a9f61b028005a4858fdac845db406aefb181
```

`hf.exe` 不会自动读取项目 `.env`，因此上面显式设置了下载源。命令使用默认 Hub 缓存，
不要以 `--local-dir` 把缓存变成另一套路径而仍让应用读取原模型 ID。
下载完成后将 `.env` 中 `EMBEDDING_WARMUP_ON_START` 改回 `true`；如果当前终端存在同名
临时变量，执行 `Remove-Item Env:EMBEDDING_WARMUP_ON_START`，然后重启启动器。
本地 CPU 加载及首次编码若超过 `EMBEDDING_TIMEOUT_SECONDS`，应按实际耗时显式调整
该预算，不能把模型加载失败当成健康空检索。

## 生产 Compose 凭据

`docker-compose.prod.yml` 不提供数据库或对象存储默认凭据。运行前必须通过部署 Secret
管理器或进程环境显式提供：

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
REDIS_PASSWORD
MINIO_ROOT_USER
MINIO_ROOT_PASSWORD
```

不要把这些值写入仓库、命令历史、支持包或 CI 日志。Compose 在任一变量缺失时会在
解析阶段失败，避免带默认口令启动生产 Adapter。

固定 MinIO 镜像不包含 `curl`，健康检查必须使用镜像内置的 `mc ready local`。Milvus
读取对象存储凭据的变量名是 `MINIO_ACCESS_KEY_ID` 与 `MINIO_SECRET_ACCESS_KEY`；Compose
把上面的 Root 凭据显式映射到这两个变量，禁止依赖 Milvus 的默认 `minioadmin`。

Redis 使用必填 `REDIS_PASSWORD` 启动 `requirepass`，应用的 `REDIS_URL` 必须携带语义相同
的 Secret。DSN/URL 中的用户名、密码必须做 percent-encoding；包含 `@:/#%` 等字符时不能
直接原样拼接。`DATABASE_URL` 同样遵守这一规则。
生产 Compose 不再声明全局固定网络名，由 Compose project 创建隔离网络，避免其他项目容器
仅凭加入 `supermew` 网络就读取父分块缓存或伪造 Run 取消事件。

后端工作流中的 `ci-only-*` 值只属于 runner 内一次性 CI 依赖，不是部署凭据，也不得被
生产环境复用。
