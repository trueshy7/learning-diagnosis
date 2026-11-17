# 成员 C 课程知识库与 RAG

本模块负责课程资料解析、切分、向量索引、受限检索、引用校验和检索评测。已按组长 `ts` 分支的 `b-internal-1` 实现主动拉取与索引状态回报，保留原有 C/D 演示接口。业务数据库、学生评分和诊断报告保存仍由 B/D 负责。

本地代码目录是 `E:\classwork_software_C\project-yjy\member-c-rag`。根目录仍来自 `yjy` 分支，其他成员的旧代码不代表组长最新版；整合时只提交本模块。对接的组长版本为 `37c05764e5041b2c47c567a4db5b950161bf6c94`。

## 本机启动

已经建立 `.venv` 并安装依赖，本机 `.env` 已配置中文模型与20份资料的向量索引。新环境用 Python 3.10 或更新版本，在 PowerShell 执行：

```powershell
cd E:\classwork_software_C\project-yjy\member-c-rag
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-chroma.txt
Copy-Item .env.example .env
```

`.env` 会自动读取，已有终端环境变量优先。本机可先用关键词模式启动，不需要密钥：

```powershell
.\.venv\Scripts\python.exe -m rag_service
```

打开 [接口文档](http://127.0.0.1:8001/docs)。默认只装载原有栈、队列两份兼容样例；它们用于 D 的旧演示，不计入本次 20 份资料。

## 导入课程资料并启用真实向量检索

停止服务后执行。第一次显式下载约 95 MB 中文 ONNX 模型，固定版本并校验 SHA256：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_model
$env:RAG_BACKEND="chroma"
$env:RAG_MODEL_PATH="data/models/bge-local"
$env:RAG_EMBEDDING_REVISION="46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
$env:RAG_SEED_ON_START="false"
.\.venv\Scripts\python.exe -m scripts.build_knowledge_index
.\.venv\Scripts\python.exe -m rag_service
```

该模式使用 FastEmbed 的 `BAAI/bge-small-zh-v1.5`、512 维向量与 Chroma 余弦检索，响应 `mode=vector_rag`。`hash_test` 仅用于无模型单元测试，响应 `vector_hash_test`，不能当作语义检索结果。缺少模型时导入不回报成功；查询故障若允许降级，返回 `keyword_fallback` 和原因。

默认导入 20 份、4 个组长已有知识点。`--include-proposed` 可在本地加上另外 8 份、4 个待确认知识点，不会在 B 创建业务目录。资料和映射说明见 [资源登记](data/knowledge/README.md)。

## 与组长后端对接

正式对接前，在 B 创建/上传资料；B 的业务 ID 是唯一权威。可使用 `scripts.import_backend_resources` 预览，将 20 份材料经现有教师接口提交后，再由 C 自动拉取。不能把本地 `c-note-*` 当成 B 已存在的资源 ID。

```powershell
# 第一次只预览；实际导入前先核对教师令牌与课程
.\.venv\Scripts\python.exe -m scripts.import_backend_resources
$env:B_URL="http://127.0.0.1:8000"
$env:B_TEACHER_TOKEN="从B登录接口取得的教师令牌"
.\.venv\Scripts\python.exe -m scripts.import_backend_resources --apply
# 与组长在 B 配置的 C_SERVICE_KEY 一致，不是教师登录令牌
$env:B_C_KEY="由组长提供的C服务密钥"
$env:RAG_DATA_PATH="data/backend-catalog.json"
$env:RAG_CHROMA_PATH="data/backend-chroma"
$env:RAG_SEED_ON_START="false"
$env:RAG_SYNC_ON_START="true"
$env:RAG_ALLOWED_COURSE_IDS="demo-course-ds-teacher-2"
.\.venv\Scripts\python.exe -m rag_service
```

C 在同一个 HTTP 进程中每 30 秒完整扫描 B 授权课程和资料，处理版本与墓碑，并回报 `ready/failed/deleted`。无需另开一个会写相同 JSON 的进程。单次离线同步可在停止 HTTP 服务后执行 `python -m scripts.sync_backend`。

D 对正式 B 资料应调用 `/internal/retrieve-scoped`，把 B 的 `resource_catalog` 转成 `resource_scope`。空范围代表没有授权资料，不是检索全库。旧 `/internal/retrieve` 保留给 `course-ds` 演示；存在 B 同步资料的课程会拒绝不带范围的旧调用。详见 [协作接口](docs/协作接口.md)。

## 验证与评测

```powershell
.\.venv\Scripts\python.exe -m scripts.check
.\.venv\Scripts\python.exe -m scripts.evaluate --backend both --output evaluation/results_comparison.json
.\.venv\Scripts\python.exe -m scripts.evaluate --backend both --extended --output evaluation/results_extended_comparison.json
.\.venv\Scripts\python.exe -m scripts.check_d_integration
```

评测固定 20 题，可回答主集和无答案集分别统计；参考资料按资源 ID 和原文摘句同时核验。比较 400/60 与 700/100 两种切分配置。模型下载、建库耗时与检索耗时分开记录；机器测量不能当作性能承诺。结果和限制见 [评测报告](docs/检索评测报告.md) 与 [当前完成情况](docs/成员C当前实现与下一阶段计划.md)。

## 数据与限制

新目录为 `data/catalog.json`，不会把原始 `data/index.json` 静默当成新版目录。旧数据可用原 `LocalIndex` 读取后按新资源清单重新导入；B 资料优先全量重新同步。索引、模型、原件备份、`.env`、虚拟环境都不提交 Git。

只运行一个写进程、一个 Uvicorn worker。进程内锁和原子文件替换不等于跨进程事务。Chroma 是可重建派生索引；重建时保留 resource/document/version，改模型维度或版本须重建。当前语料短，参数比较不充分代表长教材表现。

原文件下载仍通过 B 的鉴权接口。C 返回的是来源说明和文字/页码定位，不把本机路径作为浏览器链接。扫描 PDF、OCR、多模态、最终报告落库及真实 LLM 解释不是 C 在本次交付中冒称完成的内容。
