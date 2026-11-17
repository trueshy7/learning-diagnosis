# B/C 整合与验证

本次以 ts `37c0576` 的 B 接口为准，引入 yjy `ffece3f` 的 `member-c-rag`。
提交分支为 `B-C`，联调工作最初在 `integration/ts-yjy-bc` 完成。两个来源分支没有共同祖先，因此只移入 C 目录，保留 B 现有业务、鉴权和内部接口。
提交仅包含 C 模块、B/C 联调测试和说明；原有 `.idea/data_source_mapping.xml` 暂存删除保留在本地，不纳入本次提交。

## 可重复的自动验收

使用 Python 3.11+，在项目根目录执行：

```sh
python -m pip install -r member-b-backend/requirements-dev.txt -r member-c-rag/requirements.txt
export TEST_MYSQL_URL='mysql+pymysql://测试账号:测试密码@127.0.0.1:3306/?charset=utf8mb4'
python scripts/check_bc_integration.py
```

测试账号必须能创建、删除数据库。每项测试创建随机 `ld_resource_test_*` 库并在结束时删除，不读取 `DATABASE_URL` 的业务数据。
B/C 监听随机本机端口，C 使用临时索引；无需启动日常开发服务。
没有 `TEST_MYSQL_URL` 时入口报错退出，不把跳过当作成功。

覆盖内容：

- 真实教师登录、资料创建、C 凭证校验和课程白名单。
- C 经 HTTP 拉取 B 资料，校验摘要、持久化索引并回报 ready。
- C 经 HTTP 返回当前版本证据，校验引用，空授权范围无结果。
- 重复同步幂等，C 索引丢失后从 B ready 资料恢复且保持 document_id。
- 通过 B 发布试卷、学生提交测验，正式诊断输入只导出 ready 资料。
- B 修改资料后 pending、版本递增、目录排除、旧回报 409；C 同步新版后旧范围不可检索、旧引用失效。
- B 删除后目录立即排除，C 同步墓碑并回报 deleted，重开索引后旧版本不能复活。
- C HTTP 服务启动时的后台同步线程自动拉取并传播删除。
- B 的 MySQL 事务回滚、并发行锁、迁移重复执行及状态回报防护。

## 日常 B/C 联调

1. 先按 B 的 `.env.example` 配置 MySQL。已有数据库按 [B 内部接口说明](../member-b-backend/docs/内部数据接口与联调说明.md) 完成索引状态迁移。
2. 在 B 配置 `C_SERVICE_KEY`（至少 32 字节）、不同的 `D_SERVICE_KEY`，以及实际课程的 `C_SERVICE_COURSE_IDS`。运行 `cd member-b-backend && python -m app`。
3. 在 C 的 `.env` 配置以下内容，再运行 `cd member-c-rag && python -m rag_service`：

```dotenv
B_URL=http://127.0.0.1:8000
B_C_KEY=与B的C_SERVICE_KEY一致
RAG_SYNC_ON_START=true
RAG_SYNC_INTERVAL=5
RAG_SEED_ON_START=false
RAG_DATA_PATH=data/backend-catalog.json
RAG_ALLOWED_COURSE_IDS=填写实际课程ID
RAG_BACKEND=keyword
```

4. 教师经 B 创建资料，等待最多一轮同步，检查 B 教师详情 `index_status=ready`。
5. 调用 C `/internal/retrieve-scoped` 时必须传 `course_id` 和 `resource_scope`，每项仅包含 B 正式目录的 `resource_id/resource_version/document_id/content_hash`。不能把目录的 title 等额外字段直接传入严格模型。
6. 验证修改和删除后状态及检索结果随版本变化。只运行一个 C 写进程，启用后台同步后不要再启动离线同步命令写同一索引。

`B_C_KEY` 是 C 访问 B 的凭证；`RAG_SERVICE_KEY` 是调用方访问 C 的可选独立凭证。配置后检索请求须加对应 Bearer 头。

## 本次验证的边界

验收使用关键词后端，证明 B/C 契约、HTTP、索引持久化和版本生命周期可用。
真实中文 Embedding 模型与 Chroma 语义检索需另行安装 `requirements-chroma.txt`、准备模型并验证；未把 hash_test 或关键词结果作为真实语义检索通过。
D 的新任务接收及报告回传不在本次 B/C 验收范围。

根目录旧 `scripts/check_integration.py`、`scripts/start_services.py` 仍面向最初 B/C/D 演示，引用已移除的 `backend_service` 和旧 `/api/v1` 流程，不能用于本版正式验收。使用本文的新入口或分别启动 B/C。

C 的 pypdf 依赖已对齐 B 的 `6.21.4`，避免联合安装时与 yjy 的 `5.5.0` 固定版本冲突。

## 2026-11-17 本机验证记录

环境：Python 3.12，临时虚拟环境，MySQL 8.0 临时容器，随机端口与随机测试库。

| 检查 | 结果 |
| --- | --- |
| B：test_internal/resources/resource_files/exams/diagnosis_tasks | 282 passed |
| C：unittest discover -s tests -v | 35 passed，1 skipped（未安装可选 Chroma） |
| 新入口 check_bc_integration.py：2 项真实 B/C HTTP + 5 项 MySQL 内部接口 | 7 passed |
| 未配置 TEST_MYSQL_URL 时运行新入口 | 返回 2，提示配置，不静默跳过 |
| git diff --check | 通过 |

合计 324 项通过，1 项可选测试跳过。C 的后台自动同步和删除传播已实际运行；没有连接或修改业务数据库。
