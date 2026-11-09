# 成员 B：`gh` 分支完整前端接口对接说明

更新日期：2026-11-09  
项目：基于 RAG 与多智能体协作的个性化学习诊断与推荐系统

## 对接结论

本次依据远程 `origin/gh` 分支中的 `member-a-frontend/docs/frontend/backend-api-alignment.md`、实际 Axios 调用和 Zod 请求/响应契约，实现了该前端 `full-v1` 模式列出的 **37 个 HTTP 操作**。代码在本地项目的 `member-b-backend/backend_service/full_quiz.py`、`full_teacher.py`、`full_common.py` 和 `full_report.py`，由 `main.py` 挂载。用户原有 `group-v0` 接口继续使用 `/api/v1`。

两套协议的 `POST /attempts` 语义冲突：`group-v0` 是提交并直接计分，`full-v1` 是先创建待作答试卷。因此完整前端协议挂载在 **`/api/v2`**。`full-v1` 是前端的契约名称，不等于后端 URL 版本。`gh` 分支现有 `.env.real` 仍写 `/api/v1`；启动 `dev:real` 前，成员 A 应在 `member-a-frontend/.env.real.local` 写入：

```dotenv
VITE_API_BASE_URL=/api/v2
```

Vite 的 `/api` 代理已经覆盖 `/api/v2`，无需改代理规则。不要把 `group-v0` 的默认入口一并改成 `/api/v2`。

## 启动与联调

在项目根目录准备 Python 3.11+，安装根 `requirements.txt`，运行 `python scripts/start_services.py`；B/C/D 分别监听本机 8000/8001/8002。前端在 `gh` 分支运行 `npm run dev:real`，默认端口 5174。前端 `BACKEND_PROXY_TARGET` 默认指向 `http://127.0.0.1:8000`。演示身份：学生 `student / demo12345`，教师 `teacher / demo12345`。

可访问 `http://127.0.0.1:8000/docs` 查看所有路径。所有 `/api/v2` JSON 成功响应采用 `{ "code": "OK", "message": "成功", "data": ..., "request_id": "..." }`，失败使用对应 HTTP 状态和字符串错误码；用户数据响应带 `Cache-Control: no-store`。除登录外使用 Bearer Token。时间为 UTC ISO 8601 字符串。

### 学生侧接口

| 范围 | 已实现路径（均以 `/api/v2` 为前缀） |
| --- | --- |
| 身份 | `POST /auth/login`、`GET /auth/me`、`POST /auth/logout` |
| 课程 | `GET /courses`、`GET /courses/{id}`、`GET /courses/{id}/knowledge-points` |
| 测验 | `POST /attempts`、`GET /attempts`、`GET /attempts/{id}`、`POST /attempts/{id}/submit`、`GET /attempts/{id}/result` |
| 任务 | `GET /tasks/{id}`、`POST /tasks/{id}/retry` |
| 报告 | `GET /reports`、`GET /reports/{id}`、`GET /reports/{id}/recommendations`、`GET /reports/{id}/comparison` |
| 资料 | `GET /resources/{id}`、`GET /resources/{id}/file` |

`POST /attempts` 根据 `kind=initial|practice|retest` 创建并保存不可变题目快照，按 `client_request_id` 幂等；学生读取的题目不含答案。提交时校验 `snapshot_version`、完整题目集合和 `Idempotency-Key`，单选/多选均按答案集合完全匹配计 1 分，空选计 0 分。成绩先持久化，再触发诊断任务；D/C 不可用时成绩仍可查看，任务记录失败原因并可重试。历史服务端筛选与分页，按提交时间和稳定 ID 排序。报告、推荐和复测比较均校验本人及课程归属。

两阶段调用示例（把占位符替换为实际返回值）：

```http
POST /api/v2/attempts
Authorization: Bearer <token>
Content-Type: application/json

{"course_id":"course-ds","kind":"initial","client_request_id":"一次创建意图的唯一值"}
```

```http
POST /api/v2/attempts/<attempt_id>/submit
Authorization: Bearer <token>
Idempotency-Key: <一次提交意图的唯一值>
Content-Type: application/json

{"snapshot_version":"<创建测验返回的版本>","answers":[{"question_id":"<题目ID>","selected_option_ids":["<选项ID>"]}]}
```

提交时 `answers` 必须覆盖返回试卷的**每一道**题；未答题传 `selected_option_ids: []`。完整前端可以刷新 `GET /attempts/{id}`、`GET /tasks/{id}` 恢复当前状态。

### 教师侧接口

| 范围 | 已实现路径（均以 `/api/v2` 为前缀） |
| --- | --- |
| 学生概况 | `GET /teacher/overview`、`GET /teacher/students`、`GET /teacher/students/{student_id}/attempts`、`GET /teacher/students/{student_id}/reports/{report_id}` |
| 课程与知识点 | `PATCH /teacher/courses/{id}`、`GET /teacher/knowledge-points`、`POST /teacher/knowledge-points`、`PATCH /teacher/knowledge-points/{id}` |
| 题库 | `GET /teacher/questions`、`GET /teacher/questions/{id}`、`POST /teacher/questions`、`PATCH /teacher/questions/{id}` |
| 资源 | `GET /teacher/resources`、`GET /teacher/resources/{id}`、`POST /teacher/resources`、`PATCH /teacher/resources/{id}` |
| 上传 | `POST /teacher/documents`、`GET /teacher/documents/{id}`；任务状态与重试复用 `/tasks/{id}` |

教师操作校验课程授权；查看学生记录还校验学生选课、测验/报告归属。题目与资源停用后不进入新组卷/推荐，但已有测验快照和报告继续可读。上传使用 `multipart/form-data`：`course_id`、`title`、JSON 数组字符串 `knowledge_point_ids`、`file`。支持 UTF-8 TXT、Markdown 和可提取文字的 PDF；单文件上限 10 MiB。受理返回 202 与文档/任务 ID，后台解析并经 C 建索引；资料全文和原文件均由 B 做授权校验后提供。

## 当前实现边界

- 演示环境采用 SQLite 自动建表及演示账号；既有生产数据库需另做版本化迁移。已有演示课程会在启动时补齐演示教师和学生的课程关系，新建课程按当前演示学生分配。
- 报告的掌握度与推荐基于 D 的规则诊断，解释标记为 `rule_template`；C 当前使用关键词检索。接口不会声称已运行大模型或向量检索。
- 扫描版 PDF 不能直接提取正文，需要 OCR；损坏、加密或无正文文件在任务中记录失败。后台任务依附于 B 进程；进程重启会把未完成任务标为可重试的中断失败。
- 本次没有切换、提交或推送 Git 分支。后端代码位于当前工作区；`gh` 分支前端只需设置上述基址后才能按这套完整协议调用。合并时请保留 `/api/v1` 的旧协议及 `/api/v2` 的完整协议。

## 验证记录

在项目现有虚拟环境运行：

```sh
cd member-b-backend
../.venv/bin/python -m pytest -q -p no:cacheprovider
cd ..
.venv/bin/python scripts/check_integration.py
```

结果：后端 **12 项测试通过**；B/C/D 临时端口真实 HTTP 联调通过，包含旧接口、完整协议的快照、诊断任务和报告。另把 `gh` 分支实际 Zod 契约在临时目录中对 25 份关键响应样本执行校验，**25/25 通过**；真实 C/D 联调生成的报告也通过前端 `reportSchema`。这些验证覆盖核心数据形状与主流程；前端浏览器中的 37 项逐页验收仍需 A 在 `gh` 分支运行 `dev:real` 完成。
