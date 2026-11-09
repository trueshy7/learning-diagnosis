# 成员 B 功能扩展实现记录

项目：**基于 RAG 与多智能体协作的个性化学习诊断与推荐系统**  
范围：本次只实现成员 B 的后端业务、数据库与对 C/D 的接口。A 的界面、C 的检索算法和 D 的诊断算法仍由对应成员负责。

## 已完成的功能

| 功能 | B 端实现 | 对接方式 |
| --- | --- | --- |
| 错题本与针对性练习 | 每次提交保存题目、选项、标准答案、学生选择和判分快照；按每题最近一次结果形成错题本；练习优先取仍启用的错题，可按知识点筛选。 | A 展示错题和练习页，并在提交时传 `question_ids`。 |
| 学习进度 | 按课程返回时间线、测验/练习类别、每个知识点的样本数、答对数和正确率；只统计当前登录用户。 | A 用 `timeline` 绘制曲线，用 `knowledge_points` 绘制当前概况。 |
| 教师题库维护 | 教师可完整修改题干、选项、答案、知识点，可停用/启用题目并按状态或知识点筛选；学生取题只见启用题且看不到答案。 | A 的教师页面调用新增 PATCH 和已有列表接口。 |
| 教师知识库管理 | 资料目录存 SQL；支持文本 JSON 导入、`.txt`/`.md`/`.pdf` 文件导入、列表、状态、删除；导入与删除先调用 C，成功后更新本地目录。 | C 沿用 `/internal/ingest`、`/internal/resources/{id}`；A 负责上传和管理页面。 |
| 带引用的课程问答 | B 调 C 检索，只摘录属于本课程已登记资源的证据，并返回来源、位置和证据 ID；没有证据时明确返回 `insufficient_evidence`。 | `mode=extractive_retrieval`，当前不使用 LLM。 |

## 主要接口

所有路径以 `/api/v1` 开头，除登录外需 `Authorization: Bearer <token>`。

| 方法及路径 | 关键请求或响应 |
| --- | --- |
| GET `/courses/{course_id}/wrong-questions` | `items` 包含上次错答快照、`attempt_id`、`available_for_practice`。同题后来做对会从当前错题本移出。 |
| GET `/courses/{course_id}/practice?knowledge_point_id=kp-stack&limit=5` | 返回 `question_ids` 和不含答案的 `questions`；错题优先。 |
| POST `/attempts` | 正常测验沿用原请求；加 `question_ids` 则只按这些启用题计分，记录 `kind=practice`。 |
| GET `/attempts/{attempt_id}/review` | 返回该次提交的题目与答案快照；仅记录本人可访问。 |
| GET `/courses/{course_id}/progress` | 返回 `attempt_count`、`knowledge_points`、`timeline`，每个时间点带 `kind`、得分及知识点正确率。 |
| GET `/teacher/courses/{course_id}/questions?active=false&knowledge_point_id=...` | 教师筛选题库，包含答案和 `active`。 |
| PATCH `/teacher/courses/{course_id}/questions/{question_id}` | 完整提交 `stem`、`kind`、`options`、`correct_option_ids`、`knowledge_point_ids`。 |
| PATCH `/teacher/courses/{course_id}/questions/{question_id}/status` | `{"active":false}` 停用，`true` 启用。 |
| POST `/teacher/resources` | 既有文本导入接口，现在会在 B 的 SQL 目录记录索引状态。 |
| POST `/teacher/resources/file` | 以 JSON 传文件信息和 `content_base64`，详见下例。 |
| GET `/teacher/resources?course_id=...` | 查询资料目录；默认不含已删除资料，可加 `include_deleted=true`。 |
| GET `/teacher/resources/{resource_id}/status` | 返回 `status`、`index_version`、`chunk_count`、`updated_at`。 |
| DELETE `/teacher/resources/{resource_id}` | 先删 C 的索引，再将 B 的目录标为 `deleted`。 |
| POST `/courses/{course_id}/ask` | 检索式问答，返回 `answer`、`citations`、`status`、`index_version`。 |

练习流程示例：

```json
GET /api/v1/courses/course-ds/practice?knowledge_point_id=kp-stack&limit=2
// 从响应 data.question_ids 取得题目 ID，例如 ["q-stack-1", "q-stack-2"]

POST /api/v1/attempts
{
  "course_id": "course-ds",
  "question_ids": ["q-stack-1", "q-stack-2"],
  "answers": [
    {"question_id": "q-stack-1", "selected_option_ids": ["A"]},
    {"question_id": "q-stack-2", "selected_option_ids": ["A"]}
  ]
}
```

文件导入示例（`content_base64` 是文件原始字节的 Base64 编码）：

```json
POST /api/v1/teacher/resources/file
{
  "resource_id": "res-lesson-01",
  "document_id": "doc-lesson-01",
  "course_id": "course-ds",
  "title": "栈课程讲义",
  "filename": "stack.md",
  "content_base64": "IyDmoIjnmoTlm77op6M=",
  "knowledge_point_ids": ["kp-stack"],
  "source": "教师课程材料"
}
```

可上传 UTF-8 文本、Markdown 与可提取文字的 PDF；文件最大 2 MB，PDF 最多 100 页，提取正文最多 20 万字符。B 只把提取后的文字交给 C 建索引，不在本地保存原始文件。扫描版 PDF 需要先做 OCR。

课程问答示例：

```json
POST /api/v1/courses/course-ds/ask
{"query":"栈是什么？","knowledge_point_ids":["kp-stack"],"top_k":3}
```

返回的 `answer` 是证据原文摘录，形如 `[1] 栈是一种后进先出……`；`citations` 给出资源、文档、来源和位置。找不到可用证据时 `answer=null`、`citations=[]`、`status=insufficient_evidence`，不会编造回答。

## 数据与兼容性

- 新增 `question_states` 和 `resources` 表；它们由当前开发环境的 `create_all` 创建，已有 `questions`、`attempts` 表不需要改列。
- 停用只影响新试卷；已完成作答的题目快照和成绩保存在 `attempts.payload`，教师改题不会追改历史。
- 旧版测验没有题目快照，`review` 会给出 `snapshot_available=false`；其原有判分记录仍可用于进度统计。
- 演示资源以 `seeded` 状态加入 B 的目录；教师导入成功后为 `indexed`，删除后为 `deleted`。被删除的资源不会在 B 重启时自动恢复。
- 练习与完整测验都可以请求 D 诊断，但练习题少时 D 可能返回“证据不足”，这是预期结果。

## 测试与结果

在项目根目录执行：

```sh
cd member-b-backend
../.venv/bin/python -m pytest -q -p no:cacheprovider
cd ..
.venv/bin/python scripts/check_integration.py
```

- 后端自动测试：**9 passed**。新增用例覆盖历史快照、错题消除、练习、趋势、改题停用、角色权限、文本/Markdown/PDF 导入、C 失败不误记成功、资料删除及引用过滤。
- B/C/D 真实 HTTP 联调：**passed**。除了既有测验、诊断、推荐和复测，还检查资料目录记录及课程问答返回真实 C 证据引用。
- `pypdf==6.21.4` 已加入根目录和 B 目录的依赖清单。

## 后续协作与限制

- A 尚未接入错题页、学习曲线、教师题库与资料管理页；B 的接口已经可以在 `/docs` 中操作。
- 当前课程问答只做检索和原文摘录。真正的生成式解释应由 D/C 设计提示词、引用校验与评测后再接入。
- 尚未做版本化数据库迁移、MySQL 验证、并发提交冲突恢复、OCR 和原始文件下载；这些属于部署与下一阶段增强。
