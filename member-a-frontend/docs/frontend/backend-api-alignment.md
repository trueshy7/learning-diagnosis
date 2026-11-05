> 当前默认组仓库入口使用 group-v0，见 [实际联调文档](../group-integration.md)。本文保留为 full-v1 扩展协议提案，不能视为当前 B 已实现。

# LearnMate 前后端接口对齐文档

版本：frontend-contract-v1.1。整理日期：2026-10-23。适用工程：code/frontend。本文以实际 Axios 服务、Zod 校验、页面行为和 MSW 契约为依据，提供后端可直接据此实现的协议；当前尚未得到 B/C/D 确认，不能视为已完成真实联调。

本文给 B 完整的外部接口、鉴权、持久化、任务与错误约定；C/D 通过 B 提供数据。前端仅访问 B 的 /api/v1，不直连模型、向量库、数据库或 C/D 内部 Python 服务。mock 只用于验证交互，不代替正式计分、鉴权或算法验收。

## 1 对齐入口与职责

| 内容                                     | 当前权威入口                                           | 负责人          |
| ---------------------------------------- | ------------------------------------------------------ | --------------- |
| HTTP 路径                                | frontend/src/api/endpoints.ts                          | A/B共同确认     |
| 页面调用                                 | frontend/src/api/services/index.ts                     | A               |
| 响应 DTO / 不变量                        | frontend/src/api/contracts/index.ts                    | A/B/C/D确认语义 |
| 请求字段与条件                           | frontend/src/api/contracts/requests.ts；教师写入schema | A/B             |
| 字段适配                                 | frontend/src/api/mappers/                              | A               |
| 正式鉴权、业务库、计分、快照、报告持久化 | 由 B 实现                                              | B               |
| 文档、片段、引用与资料处理               | 经 B 输出，不向前端暴露磁盘路径或内部服务              | C/B             |
| 掌握状态、证据、推荐、版本与复测可比性   | 经 B 输出，前端不重算阈值或推荐排序                    | D/B             |

DTO 完整字段在本文附录。配套 JSON Schema 为 examples/contract-schemas.json，可通过 `npm run docs:api` 从实际 schema 更新。JSON Schema 与 TypeScript 无法表达全部跨字段/归属/事务约束，正文业务规则也必须实现。

### 实现顺序

1. 鉴权 → /courses → 课程详情。
2. 创建测验 → 快照查询 → 提交计分 → 刷新恢复。
3. 诊断任务 → 完整报告 → 来源阅读与文件。
4. 推荐练习 → 固定基准复测 → 历史与对比。
5. 教师课程/知识点/题库/资源 → 上传任务 → 学生概况与授权报告。

B 组织逐接口确认；C 核对来源字段，D 核对状态与比较含义，A 核对页面所需字段。通过 Network、request_id、数据库记录逐项核对，不用模拟截图替代真实证据。

## 2 传输与公共规则

- 默认基址 `/api/v1`，UTF-8 JSON；文件上传和下载另述。路径 ID 是不透明字符串，前端进行 URL 编码，不能根据 ID 推断权限或自增关系。
- 时间使用 UTC ISO 8601，带 `Z`，如 `2026-10-23T01:30:00Z`。界面按 Asia/Shanghai 显示。
- 除登录外带 `Authorization: Bearer <access_token>`。当前不是 Cookie 鉴权，Axios 未开启跨源 Cookie。若 B 改用 HttpOnly Cookie，需统一调整鉴权适配、CORS/CSRF 和测试，不能仅改一个环境变量。
- 成功使用 200/201/202 且 `code="OK"`；失败必须使用相应 HTTP 错误码。204 无 body 不符合本版 JSON 契约；退出等空结果返回 200 和 data:null。
- 数据结构的空集合用 `[]`，未知或不适用的值用 `null`，不能用空字符串、0 或缺失字段替代。附录中仅 `?` 字段可以省略。
- 常用分页查询 `page=1&page_size=10`，page 从 1 开始，page_size 范围 1—50。返回 `{items,total,page,page_size}`。页码超出范围时 items=[]，total仍为实际总数。
- 历史记录按 submitted_at 降序、同时间用稳定ID排序；排序必须稳定，防止翻页重复/漏记录。筛选在服务端先执行，再分页；total为筛选后的数量。
- 无分页的 /courses 返回课程数组；当前验证单课程，但不能要求前端写死 course-ds。active=false 的内容不用于新选卷/推荐，历史快照仍可查询。
- 本版 PATCH 由前端发送完整业务写入 DTO，并不只发送变化字段。服务仅接收白名单业务字段，不能将请求字典直接覆盖 ORM。
- 敏感身份、测验、成绩、报告响应及授权文件建议使用 `Cache-Control: no-store`。不得在错误或日志中返回密码、令牌、模型密钥、提示词、SQL、内部路径或服务堆栈。

### 2.1 成功和错误 envelope

```json
{ "code": "OK", "message": "成功", "data": {}, "request_id": "req-example" }
```

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请检查填写内容",
  "data": null,
  "request_id": "req-example",
  "errors": [{ "field": "title", "message": "标题不能为空" }]
}
```

request_id 由后端产生并贯穿 B/C/D 日志；前端只在本地调试界面显示，普通用户看到中文业务提示。后端遗漏标识时，客户端使用带 `local:` 前缀的本地标识，不冒充服务端日志ID。

HTTP=200但code非OK也视为失败。前端兼容 FastAPI 默认422 `{detail:[{loc:["body","title"],msg:"..."}]}`，正式实现仍请统一 envelope，不依赖兼容分支。errors只描述安全的字段问题，不放模型原始响应或校验堆栈。

### 2.2 数值与精度

| 字段                                               | 范围与约束                                                                        |
| -------------------------------------------------- | --------------------------------------------------------------------------------- |
| correct_count / question_count / total_count等计数 | 非负整数；有效试卷 total_count > 0                                                |
| raw_score / max_score                              | 本版每题1分，分别等于正确题数/有效题数；满分>0                                    |
| Score.percentage                                   | 0—100；与correct_count/total_count×100一致；允许保留两位小数，前端误差容限0.005分 |
| correct_rate / mastery_score / task.progress       | 0—1或null；不要传0—100                                                            |
| correct_rate                                       | 根据实测计数计算，建议至少6位小数；前端计数一致性容限0.0001                       |
| delta_percentage_points                            | -100—100或null；例如0.60→0.80为+20个百分点；与两次正确率相符，容限0.02个百分点    |
| estimated_minutes / retry_count / duration_ms      | 非负整数或附录指定的null                                                          |

前端只验证统计不变量和显示单位，不按0.60/0.80阈值重新诊断。正式状态以D输出的 mastery_status、coverage_reason、comparable为准。阈值、最小题量和规则变更由B/D维护rule_version并共同确认。

### 2.3 字段限制

标题、知识点名称：去首尾空白后1—100字符；题干1—2000；选项文本1—500；简介、说明、解析0—3000；正文保留换行。单题2—6个选项，至少关联1个有效知识点。单选恰好1个答案，多选至少2个，答案只能来自当前选项。

username为1—100字符；password为1—200字符，不去除密码首尾空格。client_request_id为1—200字符。practice请求question_ids为1—200个，服务端仍需检查真实可用范围与资源归属。

## 3 角色与资源归属

| 操作                              | student                        | teacher                                              |
| --------------------------------- | ------------------------------ | ---------------------------------------------------- |
| 课程与可用资料                    | 本人授权课程范围               | 本人授权课程范围                                     |
| 创建/提交测验                     | 仅本人                         | 不代学生提交，本版不调用                             |
| /attempts/:id、本人报告、诊断任务 | 仅本人记录                     | 使用专用教师授权报告入口，不假定本人接口可读学生数据 |
| /teacher/*                        | 403                            | 校验所授课程与指定学生范围                           |
| 文档上传与处理任务                | 403                            | 仅本人授权课程                                       |
| 文件与引用定位                    | 校验资源、课程、文档、片段关系 | 同样校验，不接受任意磁盘路径                         |

user_id来自服务端验证的身份，不信任请求体/URL自填角色。教师的studentId与reportId必须互相匹配，且在其授权课程。普通学生不能通过更换ID读取他人attempt/report/task。学生题目 DTO 不包含标准答案、解析、correct_option_ids 或提交前 is_correct，即便隐藏在DOM或props中也不允许。

## 4 接口目录

“主”是当前页面实际依赖；“补充”已由模拟契约提供、可供查询或后续拆分，本次页面主要使用完整DTO，不能因补充接口另算一份结果。所有路径均省略 /api/v1。

| 编号 | 方法与路径                                      | 身份          | 用途 | 成功data                                 |
| ---- | ----------------------------------------------- | ------------- | ---- | ---------------------------------------- |
| A01  | POST /auth/login                                | 无            | 主   | LoginResponse，200                       |
| A02  | GET /auth/me                                    | 登录          | 主   | UserDTO，200                             |
| A03  | POST /auth/logout                               | 登录          | 主   | null，200                                |
| C01  | GET /courses                                    | 登录          | 主   | CourseDTO[]，200                         |
| C02  | GET /courses/:courseId                          | 登录          | 主   | CourseDTO，200                           |
| C03  | GET /courses/:courseId/knowledge-points         | 登录          | 补充 | KnowledgePointDTO[]，200                 |
| T01  | POST /attempts                                  | 学生          | 主   | AttemptDTO，201                          |
| T02  | GET /attempts                                   | 学生本人      | 补充 | Page<HistoryItemDTO>，200                |
| T03  | GET /attempts/:attemptId                        | 学生本人      | 主   | AttemptDTO，200                          |
| T04  | POST /attempts/:attemptId/submit                | 学生本人      | 主   | SubmitAttemptResponse，200               |
| T05  | GET /attempts/:attemptId/result                 | 学生本人      | 补充 | AttemptResultDTO，200                    |
| J01  | GET /tasks/:taskId                              | 本人/授权教师 | 主   | TaskDTO，200                             |
| J02  | POST /tasks/:taskId/retry                       | 本人/授权教师 | 主   | TaskDTO，202                             |
| R01  | GET /reports                                    | 学生本人      | 主   | Page<HistoryItemDTO>，200                |
| R02  | GET /reports/:reportId                          | 学生本人      | 主   | ReportDTO，200                           |
| R03  | GET /reports/:reportId/recommendations          | 学生本人      | 补充 | RecommendationsResponse，200             |
| R04  | GET /reports/:reportId/comparison               | 学生本人      | 补充 | ComparisonDTO或null，200                 |
| F01  | GET /resources/:resourceId                      | 登录且授权    | 主   | ResourceDetailDTO，200                   |
| F02  | GET /resources/:resourceId/file                 | 登录且授权    | 主   | 二进制，200；失败JSON                    |
| M01  | GET /teacher/overview                           | 教师          | 主   | OverviewDTO，200                         |
| M02  | GET /teacher/students                           | 教师          | 主   | Page<TeacherStudentDTO>，200             |
| M03  | GET /teacher/students/:userId/attempts          | 教师          | 主   | Page<HistoryItemDTO>，200                |
| M04  | GET /teacher/students/:userId/reports/:reportId | 教师          | 主   | ReportDTO，200                           |
| M05  | PATCH /teacher/courses/:courseId                | 教师          | 主   | CourseDTO，200                           |
| K01  | GET /teacher/knowledge-points                   | 教师          | 主   | Page<KnowledgePointDTO>，200             |
| K02  | POST /teacher/knowledge-points                  | 教师          | 主   | KnowledgePointDTO，201                   |
| K03  | PATCH /teacher/knowledge-points/:id             | 教师          | 主   | KnowledgePointDTO，200                   |
| Q01  | GET /teacher/questions                          | 教师          | 主   | Page<TeacherQuestionDTO>，200            |
| Q02  | GET /teacher/questions/:id                      | 教师          | 补充 | TeacherQuestionDTO，200                  |
| Q03  | POST /teacher/questions                         | 教师          | 主   | TeacherQuestionDTO，201                  |
| Q04  | PATCH /teacher/questions/:id                    | 教师          | 主   | TeacherQuestionDTO，200                  |
| U01  | GET /teacher/resources                          | 教师          | 主   | Page<TeacherResourceListItemDTO>，200    |
| U02  | GET /teacher/resources/:id                      | 教师          | 主   | ResourceDetailDTO，200（可读停用元数据） |
| U03  | POST /teacher/resources                         | 教师          | 主   | ResourceDetailDTO，201                   |
| U04  | PATCH /teacher/resources/:id                    | 教师          | 主   | ResourceDetailDTO，200                   |
| D01  | POST /teacher/documents                         | 教师          | 主   | UploadResponse，202                      |
| D02  | GET /teacher/documents/:id                      | 教师          | 补充 | DocumentDTO，200                         |

RecommendationsResponse = {report_id:string,attempt_id:string,recommendations:RecommendationDTO[],actions:{can_retest:boolean,can_practice:boolean}}。UploadResponse = {document:DocumentDTO,task:TaskDTO}。

## 5 鉴权与课程

### A01 POST /auth/login

body为LoginRequest，不接收role/user_id。账号错误返回401 INVALID_CREDENTIALS；不得返回密码散列或token签名密钥。

```json
{ "username": "student-account", "password": "user-entered-password" }
```

```json
{
  "code": "OK",
  "message": "成功",
  "request_id": "req-login",
  "data": {
    "access_token": "opaque-example-token",
    "token_type": "Bearer",
    "expires_at": "2026-10-23T03:30:00Z",
    "user": {
      "user_id": "usr-001",
      "username": "student-account",
      "display_name": "学生示例",
      "role": "student"
    }
  }
}
```

示例不是正式凭证。前端把令牌放当前标签sessionStorage，再调用/me取得最终角色；不从token字符串或URL推断角色。B确认令牌TTL、过期/吊销和退出语义；当前无自动刷新令牌。

### A02 GET /auth/me 与 A03 POST /auth/logout

/me验证令牌及当前角色，返回UserDTO。启动时前端共享一次身份初始化。401会清私有状态并回登录，403保留身份。logout body为空，返回data:null；后端撤销会话，前端即使请求失败也清本地会话。正式服务应考虑重复退出的幂等行为。

### C01—C03

课程只返回当前账号授权课程。Course.knowledge_points是实际目录，数组可以是8—12项或后续扩展长度，不依赖固定ID。Course.active_attempt_id是可继续作答的一次测验，刷新课程不创建试卷。latest_attempt_id/latest_report_id属于当前学生；教师入口可为空，不借用任意学生记录。

无课程返回[]，未知课程404，未授权课程403或统一不泄漏存在性的404，需全组固定策略。停用知识点的历史名称由报告/快照保留。

## 6 测验与计分

### T01 POST /attempts

body为CreateAttemptRequest，返回服务选卷后的AttemptDTO。三种创建意图：

```json
{
  "course_id": "course-example",
  "kind": "initial",
  "client_request_id": "create-intent-001"
}
```

```json
{
  "course_id": "course-example",
  "kind": "practice",
  "client_request_id": "create-intent-002",
  "source_report_id": "report-example",
  "question_ids": ["question-07", "question-08"]
}
```

```json
{
  "course_id": "course-example",
  "kind": "retest",
  "client_request_id": "create-intent-003",
  "source_report_id": "report-example",
  "baseline_attempt_id": "attempt-baseline"
}
```

- initial：不接受指定题目、来源报告、基准或答案，由服务选题。
- practice：source_report_id与question_ids必填，只允许该报告推荐的可用候选题；不携带baseline。
- retest：source_report_id与baseline_attempt_id必填，不指定question_ids；两者必须指向本人同课程的同一次已提交测验，由服务选择复测题。
- client_request_id标识一个用户的一次创建意图。相同意图重试返回原attempt，不新建。相同标识不同有效载荷409；换一种练习或切换练习/复测属于新意图。
- 试卷保存题干、选项及其真实option_id、题型、知识点、难度和答案快照。教师后续编辑不追改已有快照。题量由服务返回，前端按数组渲染；演示24题不是正式接口必须写死的长度。
- 题库不足或没有合法练习返回明确业务错误，不能返回空questions或假装创建成功。

### T03 GET /attempts/:id

这是刷新恢复的权威入口。in_progress时result/submitted_at/diagnosis_task_id/report_id应为null；submitted时必须有持久化result、提交时间和任务ID。submitted不能回到可编辑状态。

同一question_id在questions中仅一次。选项ID稳定，不用A/B字母或数组下标当业务ID。result.grades中的题目必须属于对应快照。

### T04 POST /attempts/:id/submit

Header额外带`Idempotency-Key`。body为SubmitAttemptRequest：

```json
{
  "snapshot_version": "snapshot-example-v1",
  "answers": [
    { "question_id": "question-01", "selected_option_ids": ["option-01-a"] },
    { "question_id": "question-02", "selected_option_ids": [] }
  ]
}
```

示例展示两题的完整提交形式；实际必须覆盖服务返回试卷的每道题且仅一次。未答用[]。服务校验题目/选项范围、单选数量和快照版本。多选集合顺序不同视为相同语义。

计分冻结规则：每题1分，答案集合完全匹配才得分；少选、错选、已提交卷内未答均为0，不给部分分。总分使用不同有效题；一题多知识点在各点分别计入，知识点题数不能再相加当总题数。

提交必须原子完成：冻结答案 → 保存唯一成绩 → 保存提交时间 → 绑定唯一诊断任务。成功响应时这些内容已经可查询，不能先回成功再异步落库。外部模型失败不得回滚成绩。

相同key且相同语义返回原SubmitAttemptResponse；已提交后相同答案的重复提交也可返回原成功结果。相同key不同答案或已提交后不同答案409，不覆盖旧成绩、不新建第二个任务。

SubmitAttemptResponse中attempt_id/result.attempt_id必须与请求一致；result.rule_version、graded_answers及score与后续GET完全一致。

### 提交响应丢失恢复

前端锁定答案，保留原key/请求，不立即创建新卷。先GET同attempt：submitted恢复成绩；in_progress允许原key/内容重试或明确返回编辑；查询失败继续待确认。刷新后也先GET权威状态，再恢复经过校验的提交意图。前端不会据网络超时推断服务未提交。

### T02/T05

T02接受course_id、kind、page、page_size，本版模拟返回已提交历史摘要；如需要查询未提交列表，B需另行确认状态筛选与返回结构。T05未提交返回409 ATTEMPT_NOT_SUBMITTED，已提交返回同一持久化结果。

## 7 异步任务与报告

### J01 GET /tasks/:id

状态机：queued → running → completed或failed；受控重试可从failed回queued。禁止用HTTP=500替代一个业务上已知的failed任务。GET成功返回TaskDTO，服务错误另走envelope。

- diagnosis绑定attempt_id，document_id=null；completed必须有report_id，且此时报告已可GET。
- document_ingestion绑定document_id，不要求report_id；完成后相应资源状态更新，文件/正文按实际能力可读。
- progress若有值为0—1，是服务真实进度；不能伪造百分比，无进度用null。
- current_step/error_message只返回可公开的业务描述，不放内部调用链、路径、提示词或模型原始异常。前端普通页按status/error_code生成提示，开发模式才展示部分追踪信息。

```json
{
  "code": "OK",
  "message": "成功",
  "request_id": "req-task",
  "data": {
    "task_id": "task-example",
    "kind": "diagnosis",
    "status": "completed",
    "attempt_id": "attempt-example",
    "document_id": null,
    "report_id": "report-example",
    "progress": 1,
    "current_step": "学习报告已生成",
    "error_code": null,
    "error_message": null,
    "can_retry": false,
    "retry_count": 0,
    "created_at": "2026-10-23T01:30:00Z",
    "updated_at": "2026-10-23T01:30:05Z"
  }
}
```

前端默认每次响应完成后等待1500ms再查询，最多40次/60秒；单次HTTP默认10秒。终态、网络失败、401/403、切页、退出和达到上限均停止；总时限可以取消在途请求。等待上限不是服务failed，可手动查询下一轮。

### J02 POST /tasks/:id/retry

body={}，必须携带Idempotency-Key。仅can_retry=true时允许；服务返回当前任务，不新建测验或覆盖其他轮次。重复同key不增加retry_count。前端每次人工重试生成一个key，B维护重试策略和上限，演示上限2次仅是模拟设置，不是正式生产容量承诺。

### R01 GET /reports

查询course_id、kind、page、page_size。列表包含所有本人已提交测验摘要，即使诊断失败/处理中而report_id=null，也要可见成绩与diagnosis_task_id/status，不能把失败记录静默隐藏。HistoryItemDTO中无报告、无分数等使用null；排序见公共规则。

### R02 GET /reports/:id

返回完整ReportDTO，包括统计、引用、推荐和比较。它是当前报告页/推荐页主要使用的组合接口。前端会核对请求report_id、当前用户、关联attempt的user/course/rule_version及总成绩，矛盾时不展示旧报告伪装成功。

知识点约定：

- 0题：correct_count=0，correct_rate/mastery_score=null，状态insufficient_evidence，reason=not_tested。
- 覆盖不足但有观测：例如2/2，correct_rate=1、mastery_score=null，insufficient_evidence、too_few_questions。不能标已掌握，也不画成0掌握。
- 足够覆盖：由D返回weak/consolidating/mastered、正确率与掌握值，coverage_reason=null。默认组内规则有效不同题>=3，阈值0.60/0.80，但须版本化并由D确认。
- wrong_question_ids去重，数量与该点错误题数一致；correct_rate与correct_count/question_count一致。
- 测验覆盖不足、检索无资料、模型降级是三种独立状态，不能合成同一个“证据不足”。

解释与证据：source_mode正式为backend，演示才为mock。explanation_mode=rule_template不代表模型成功；is_degraded与原因必须真实。cached表示可追溯的旧结果，必须额外提供cached_from{report_id,report_version,generated_at}；其他模式可省略/置null。agent_steps只能包含真实已执行摘要，未提供返回[]，不能伪造步骤或耗时。

所有evidence_ids必须属于本份evidences；知识点/证据标识不重复。每条证据必须映射到真实resource/document/chunk与版本、正文片段和可定位章节/页码。推荐中的resource/question来自可用目录。失效历史来源可以保留标题与片段并标availability，但不得进入新推荐。

### R03/R04

推荐拆分接口返回与完整Report相同版本的recommendations/actions；比较拆分接口返回相同comparison或null。不得重复调用模型生成相互矛盾的两份结果。

比较由D/B判断同用户、同课程、同知识点覆盖、规则和难度条件。不可比项delta必须null且有reason；comparable=true时两次正确率/题量和delta均需有效。局部可比不自动代表整卷可比。comparison.current_attempt_id等于报告attempt_id，baseline必须是持久化关联，不能由URL任意替换。变化不作为教学因果效果证明。

## 8 资料、引用与文件

### F01 GET /resources/:id

可选query：document_id、chunk_id、resource_version。引用跳转会带报告保存的三个定位字段。服务校验它们属于请求资源、指定历史版本及当前授权课程；不是任意路径读取接口。若旧版本可保留，应返回对应旧版内容；不能提供旧版时返回410，不静默打开内容不同的新版本。当前模拟不保存全量旧版本，版本不一致返回410。返回ResourceDetailDTO，正文text_content与外部external_url按kind提供，无值为null。

资料已停用/移除返回410 RESOURCE_REMOVED，未授权403，未找到404，仍在处理可返回409 REFERENCE_CONFLICT。历史报告中的引用片段不因此删除。教师编辑停用资源应使用U02获取元数据，不绕过学生来源访问限制。

external_url仅http/https，不允许javascript/data/file或包含用户名密码的URL。前端转义显示文本，不执行HTML或资料中的命令。Markdown/PDF解析是C/B的正式职责，当前前端没有承诺支持任意富文本。

### F02 GET /resources/:id/file

成功返回二进制，不套JSON envelope。允许类型application/pdf、text/plain、text/markdown、application/octet-stream；禁止把HTML登录页、SVG、JS或未知Content-Type当文件成功返回。空文件成功也会被拒绝。文件内容和真实MIME最终由B/C验证，不能仅信任上传扩展名。

返回正确Content-Type、Content-Disposition: attachment；适当的X-Content-Type-Options: nosniff及Cache-Control。失败返回正常HTTP错误码及JSON envelope，尤其过期401不得伪装为200 HTML。前端会先处理401，再解析Blob错误；不会把错误JSON下载成PDF。

前端通过Bearer获取Blob，令牌不拼URL；Blob地址只在页面生命周期内保存并释放。ResourceDetailDTO可额外返回filename（建议上传文档提供，元数据编辑时保留），用于安全下载名称；缺失时按标题和MIME补扩展名，前端清理路径及不安全字符。下载链接不新开可执行文档窗口。如果B使用短期授权URL，需要在资源adapter统一实现来源校验和过期重新获取，当前默认契约是二进制接口。

## 9 教师维护与查询

### M01—M04

- M01查询course_id，返回OverviewDTO；无测验平均分为null，不能补假统计。
- M02查询course_id、q（姓名/账号）、page、page_size，返回TeacherStudentDTO分页；latest_*是该学生的记录。
- M03查询course_id、page、page_size，返回指定学生历史。前端已支持逐页查询，不再用“最多50条”冒充全部。切换学生时前一请求不能覆盖新列表。
- M04报告必须属于路径指定学生与教师授权课程，返回同一持久化ReportDTO；前端不使用学生本人报告接口冒充教师权限。教师页只读，不代学生创建练习/复测。

### M05 课程

PATCH body=CourseWriteDTO{title,description}。仅编辑当前课程，不新增多课程管理或物理删课。返回保存后的完整CourseDTO，前端以响应刷新表单，不先假显示成功。

### K01—K03 知识点

查询course_id、q、active(true/false字符串)、page、page_size。写入KnowledgePointWriteDTO。名称trim、课程内重名409 DUPLICATE_NAME；不能把现有点迁移到别的课程。停用采用active=false，历史名称保留；仍有启用题目等关联的冲突返回409 REFERENCE_CONFLICT，并由组内确认允许的停用策略。

### Q01—Q04 题库

查询course_id、type、knowledge_point_id、active、page、page_size。教师响应可包含标准答案，学生响应使用独立DTO。

写入TeacherQuestionWriteDTO：

```json
{
  "course_id": "course-example",
  "type": "single_choice",
  "stem": "栈通常遵循什么原则？",
  "options": [
    {
      "option_id": null,
      "client_key": "form-a",
      "label": "A",
      "text": "后进先出"
    },
    {
      "option_id": null,
      "client_key": "form-b",
      "label": "B",
      "text": "先进先出"
    }
  ],
  "correct_option_keys": ["form-a"],
  "knowledge_point_ids": ["kp-stack-example"],
  "difficulty": "easy",
  "explanation": "插入与删除均在栈顶进行。",
  "active": true
}
```

client_key是一次表单内稳定唯一键，答案引用它；新选项option_id=null，由后端生成真实ID；编辑保留原选项ID并校验属于本题，不能拿另一题的option_id。响应只返回真实options与correct_option_ids，不返回correct_option_keys/client_key等临时写入字段。删除选项会同步移除答案引用，标签A/B会重排，但业务ID不变。

至少一个有效知识点；single_choice恰好一个正确项，multiple_choice至少两个且都属于当前选项。保存产生新version，历史attempt快照与旧报告不可追改。停用不物理删除历史；启用不足无法选卷时返回明确错误。

### U01—U04 资源

列表查询course_id、kind、knowledge_point_id、active、page、page_size。TeacherResourceListItemDTO必须包含document_id与ingestion_task_id/error字段，让刷新后的页面能够找回处理任务。

U02仅教师可读元数据，包括停用/失败/处理中资源，以便编辑或恢复；F01仍按可读来源规则返回410/409，二者语义不同。

POST只创建note/external；document必须上传创建。写入ResourceWriteDTO，note必须有正文，external必须有安全URL。PATCH document只更新标题/说明/关联/难度/启用状态，不接受客户端伪造document_id、处理成功状态、磁盘路径或正文解析结果。恢复启用时根据实际文档处理状态恢复availability，不能将失败文档直接变可用。

所有编辑失败保留表单；停用通过列表按钮或编辑表单都会确认。关联知识点和资源状态最终由后端验证，前端校验只是体验。

## 10 文档上传

### D01 POST /teacher/documents

multipart/form-data，字段course_id:string、title:string、knowledge_point_ids:JSON字符串数组、file:二进制。前端使用FormData，不手工设置boundary。

默认单文件10MiB，TXT/MD/文本型PDF，正式允许类型/大小由B/C确认并在服务端复验。空文件、无文本/扫描件、加密PDF、格式不支持、超限等返回独立错误；上传受理后解析失败应成为failed任务，不是伪装上传成功并可推荐。

成功202，data=UploadResponse。原文件/文档元信息/task先持久化，再返回受理；只有处理完成后资源available。刷新可通过列表的ingestion_task_id/document_id查询，不依赖上一页临时对象。再次上传创建新文档/版本，不覆盖历史引用。

客户端取消可能发生在服务器已经受理之后，不能承诺撤回。前端会提示取消并要求刷新列表确认；若需要真正取消处理任务，双方需另定义取消API，本版没有该接口。

### D02 GET /teacher/documents/:id

返回DocumentDTO的文件名、大小、类型、版本、task_id、状态、错误与创建时间，验证教师课程归属。重试使用J02。正式C处理链必须保证失败数据不进入可用索引/推荐。

## 11 错误码与界面行为

| HTTP | code                                                                             | 前端行为                                       |
| ---- | -------------------------------------------------------------------------------- | ---------------------------------------------- |
| 401  | INVALID_CREDENTIALS                                                              | 登录表单提示，不触发旧会话过期流程             |
| 401  | AUTH_REQUIRED / TOKEN_EXPIRED                                                    | 清私有会话、取消旧请求、回登录；文件接口也相同 |
| 403  | FORBIDDEN                                                                        | 保留合法会话，显示无权访问                     |
| 404  | NOT_FOUND / ATTEMPT_NOT_FOUND / REPORT_NOT_FOUND                                 | 显示找不到内容及返回入口                       |
| 409  | ATTEMPT_ALREADY_SUBMITTED                                                        | 查询权威测验并恢复结果，不覆盖原答案           |
| 409  | SNAPSHOT_MISMATCH                                                                | 重新加载快照，不自动重算或新建卷               |
| 409  | ATTEMPT_NOT_SUBMITTED / TASK_NOT_RETRYABLE / REFERENCE_CONFLICT / DUPLICATE_NAME | 显示可理解的业务提示，保留表单/成绩            |
| 410  | RESOURCE_REMOVED                                                                 | 提示来源失效，保留历史引用片段                 |
| 413  | FILE_TOO_LARGE                                                                   | 文件超限提示                                   |
| 415  | UNSUPPORTED_FILE_TYPE                                                            | 类型提示                                       |
| 422  | VALIDATION_ERROR / INVALID_OPTIONS / INVALID_BASELINE                            | 校验失败，不假成功                             |
| 503  | SERVICE_UNAVAILABLE                                                              | 服务暂不可用，可受控重试                       |

任务error_code另可有NO_TEXT、PARSING_FAILED、ENCRYPTED_DOCUMENT、MODEL_UNAVAILABLE等，需B/C/D确认枚举，前端未知任务错误只显示安全通用提示。MOCK_PROCESSING_FAILED/MOCK_ERROR/UNIMPLEMENTED_API仅属于本地模拟，不要求正式后端复制这些码。

客户端自有REQUEST_TIMEOUT/NETWORK_ERROR/REQUEST_CANCELLED/INVALID_RESPONSE并非后端业务码。普通界面不直接回显任意message、schema字段路径、请求ID、版本号或内部调用状态；完整错误留在受控服务日志，必要时本地联调查看。不能把成功错误码混用来控制页面。

## 12 部署与联调门禁

本地展示模式5173使用示例数据，无开发面板；调试模式5175仅本地可用；真实模式5174经Vite代理指向B。静态生产构建在dist/real，没有Vite代理，B需配置同源/api/v1转发和前端history fallback，API错误不能回退成index.html。

若跨域部署，明确允许的前端origin、Authorization/Content-Type/Idempotency-Key请求头与OPTIONS；当前Cookie凭证默认关闭。生产使用HTTPS。子目录部署需要集中调整Vite base、Router和worker地址后重新验证，当前仅验证根路径。

| 门禁           | 检查                                                          | 当前正式状态 |
| -------------- | ------------------------------------------------------------- | ------------ |
| 契约确认       | B确认路径/字段/权限/分页；C确认来源/文件；D确认统计/降级/比较 | 待全组确认   |
| 登录课程       | 真实账号/me/角色、无课程/401/403                              | 待B          |
| 测验持久化     | 实际答案、完全匹配计分、幂等、快照、响应丢失后恢复            | 待B          |
| 报告与证据     | 真实C/D结果、唯一attempt归属、图表与数据逐项核对              | 待B/C/D      |
| 复测与历史     | 固定baseline、分页、可比/不可比、跨用户拒绝                   | 待B/D        |
| 教师与上传     | 写入刷新、旧快照、受理/失败/可读/重试/版本                    | 待B/C        |
| 正常与故障闭环 | 一次真实正常模型链路及一次降级、真实权限与引用验证            | 待全组       |
| 发布           | 干净环境部署、HTTPS、代理、真实构建无mock、无密钥             | 待B组织      |

变更流程：登记差异与受影响调用方 → 更新本文/schema/样例 → A集中改adapter → 契约测试 → 逐步真实联调 → 保存脱敏证据和request_id。新增字段优先可选；删除/改义需所有调用方确认。不得把临时fixture成功当真实集成通过。

<!-- GENERATED_DTO_REFERENCE -->

## 附录 完整 DTO 字段

此附录由实际Zod契约生成；`?`表示可省略，`| null`表示字段存在但值可为空。数字范围、精度与跨字段规则以前文为准。对象未知非关键字段通常被前端忽略，StudentQuestionDTO严格拒绝任何额外字段。请求条件必填与业务校验不能只靠TypeScript表达。

```typescript
export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T | null;
  request_id: string;
  errors?: Array<{ field: string; message: string }>;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserDTO {
  user_id: string;
  username: string;
  display_name: string;
  role: 'student' | 'teacher';
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'Bearer';
  expires_at: string;
  user: UserDTO;
}

export interface KnowledgePointDTO {
  knowledge_point_id: string;
  course_id: string;
  name: string;
  description: string;
  sort_order: number;
  active: boolean;
}

export interface CourseDTO {
  course_id: string;
  title: string;
  description: string;
  knowledge_points: Array<KnowledgePointDTO>;
  latest_attempt_id: string | null;
  active_attempt_id: string | null;
  latest_report_id: string | null;
}

export interface OptionDTO {
  option_id: string;
  label: string;
  text: string;
}

export interface StudentQuestionDTO {
  question_id: string;
  type: 'single_choice' | 'multiple_choice';
  stem: string;
  options: Array<OptionDTO>;
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
}

export interface AnswerDTO {
  question_id: string;
  selected_option_ids: Array<string>;
}

export interface ScoreDTO {
  correct_count: number;
  total_count: number;
  raw_score: number;
  max_score: number;
  percentage: number;
}

export interface AttemptResultDTO {
  attempt_id: string;
  score: ScoreDTO;
  graded_answers: Array<{
    question_id: string;
    selected_option_ids: Array<string>;
    is_correct: boolean;
  }>;
  rule_version: string;
}

export interface AttemptDTO {
  attempt_id: string;
  user_id: string;
  course_id: string;
  kind: 'initial' | 'practice' | 'retest';
  baseline_attempt_id: string | null;
  source_report_id: string | null;
  status: 'in_progress' | 'submitted';
  snapshot_version: string;
  created_at: string;
  submitted_at: string | null;
  questions: Array<StudentQuestionDTO>;
  result: AttemptResultDTO | null;
  diagnosis_task_id: string | null;
  report_id: string | null;
}

export interface CreateAttemptRequest {
  course_id: string;
  kind: 'initial' | 'practice' | 'retest';
  client_request_id: string;
  baseline_attempt_id?: string;
  source_report_id?: string;
  question_ids?: Array<string>;
}

export interface SubmitAttemptRequest {
  snapshot_version: string;
  answers: Array<AnswerDTO>;
}

export interface SubmitAttemptResponse {
  attempt_id: string;
  submitted_at: string;
  result: AttemptResultDTO;
  diagnosis_task_id: string;
}

export interface TaskDTO {
  task_id: string;
  kind: 'diagnosis' | 'document_ingestion';
  status: 'queued' | 'running' | 'completed' | 'failed';
  attempt_id: string | null;
  document_id: string | null;
  report_id: string | null;
  progress: number | null;
  current_step: string | null;
  error_code: string | null;
  error_message: string | null;
  can_retry: boolean;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgePointResultDTO {
  knowledge_point_id: string;
  name: string;
  correct_count: number;
  question_count: number;
  correct_rate: number | null;
  mastery_score: number | null;
  mastery_status:
    'weak' | 'consolidating' | 'mastered' | 'insufficient_evidence';
  coverage_reason: 'not_tested' | 'too_few_questions' | null;
  wrong_question_ids: Array<string>;
  explanation: string;
  evidence_ids: Array<string>;
}

export interface EvidenceDTO {
  evidence_id: string;
  resource_id: string;
  document_id: string;
  chunk_id: string;
  document_title: string;
  knowledge_point_ids: Array<string>;
  text: string;
  location: {
    page_start: number | null;
    page_end: number | null;
    section: string | null;
  };
  source_label: string;
  resource_version: string;
  availability: 'available' | 'removed' | 'unknown';
}

export interface ResourceSummaryDTO {
  resource_id: string;
  course_id: string;
  title: string;
  kind: 'note' | 'document' | 'external';
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  active: boolean;
  availability: 'available' | 'processing' | 'failed' | 'removed';
  source_label: string;
}

export interface ResourceDetailDTO {
  resource_id: string;
  course_id: string;
  title: string;
  kind: 'note' | 'document' | 'external';
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  active: boolean;
  availability: 'available' | 'processing' | 'failed' | 'removed';
  source_label: string;
  description: string;
  document_id: string | null;
  resource_version: string;
  text_content: string | null;
  external_url: string | null;
  file_available: boolean;
  filename?: string | null;
  location: {
    page_start: number | null;
    page_end: number | null;
    section: string | null;
  } | null;
}

export interface RecommendationDTO {
  recommendation_id: string;
  knowledge_point_id: string;
  priority: number;
  reason: string;
  next_step: string;
  estimated_minutes: number | null;
  evidence_ids: Array<string>;
  resources: Array<ResourceSummaryDTO>;
  practice_questions: Array<{
    question_id: string;
    title: string;
    type: 'single_choice' | 'multiple_choice';
  }>;
}

export interface ComparisonPointDTO {
  knowledge_point_id: string;
  name: string;
  comparable: boolean;
  reason: string | null;
  baseline_correct_rate: number | null;
  current_correct_rate: number | null;
  baseline_question_count: number;
  current_question_count: number;
  delta_percentage_points: number | null;
  difficulty_note: string;
}

export interface ComparisonDTO {
  baseline_attempt_id: string;
  current_attempt_id: string;
  baseline_rule_version: string;
  current_rule_version: string;
  overall_comparable: boolean;
  overall_reason: string | null;
  overall_delta_percentage_points: number | null;
  knowledge_points: Array<ComparisonPointDTO>;
}

export interface ReportDTO {
  report_id: string;
  attempt_id: string;
  user_id: string;
  course_id: string;
  generated_at: string;
  report_version: string;
  rule_version: string;
  data_version: string;
  source_mode: 'mock' | 'backend';
  explanation_mode: 'llm' | 'rule_template' | 'cached';
  cached_from?: {
    report_id: string;
    report_version: string;
    generated_at: string;
  } | null;
  is_degraded: boolean;
  degraded_reasons: Array<string>;
  retrieval_status: 'available' | 'empty' | 'failed' | 'not_requested';
  score: ScoreDTO;
  summary: string;
  knowledge_points: Array<KnowledgePointResultDTO>;
  evidences: Array<EvidenceDTO>;
  recommendations: Array<RecommendationDTO>;
  comparison: ComparisonDTO | null;
  agent_steps: Array<{
    step: 'diagnosis' | 'retrieval' | 'recommendation';
    status: 'completed' | 'skipped' | 'failed';
    summary: string;
    duration_ms: number | null;
  }>;
  actions: { can_retest: boolean; can_practice: boolean };
}

export interface HistoryItemDTO {
  attempt_id: string;
  report_id: string | null;
  kind: 'initial' | 'practice' | 'retest';
  baseline_attempt_id: string | null;
  submitted_at: string | null;
  score: ScoreDTO | null;
  diagnosis_task_id: string | null;
  diagnosis_status: 'queued' | 'running' | 'completed' | 'failed' | null;
}

export interface TeacherQuestionDTO {
  question_id: string;
  type: 'single_choice' | 'multiple_choice';
  stem: string;
  options: Array<OptionDTO>;
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  course_id: string;
  correct_option_ids: Array<string>;
  explanation: string;
  active: boolean;
  version: string;
}

export interface CourseWriteDTO {
  title: string;
  description: string;
}

export interface KnowledgePointWriteDTO {
  course_id: string;
  name: string;
  description: string;
  sort_order: number;
  active: boolean;
}

export interface TeacherQuestionWriteDTO {
  course_id: string;
  type: 'single_choice' | 'multiple_choice';
  stem: string;
  options: Array<{
    option_id: string | null;
    client_key: string;
    label: string;
    text: string;
  }>;
  correct_option_keys: Array<string>;
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  explanation: string;
  active: boolean;
}

export interface ResourceWriteDTO {
  course_id: string;
  title: string;
  description: string;
  kind: 'note' | 'external' | 'document';
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  active: boolean;
  text_content: string | null;
  external_url: string | null;
}

export interface UploadMetadataDTO {
  course_id: string;
  title: string;
  knowledge_point_ids: Array<string>;
}

export interface DocumentDTO {
  document_id: string;
  resource_id: string;
  course_id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  version: string;
  task_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface TeacherResourceListItemDTO {
  resource_id: string;
  course_id: string;
  title: string;
  kind: 'note' | 'document' | 'external';
  knowledge_point_ids: Array<string>;
  difficulty: 'easy' | 'medium' | 'hard';
  active: boolean;
  availability: 'available' | 'processing' | 'failed' | 'removed';
  source_label: string;
  document_id: string | null;
  ingestion_task_id: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface OverviewDTO {
  course_id: string;
  student_count: number;
  submitted_attempt_count: number;
  average_percentage: number | null;
  recent_attempts: Array<HistoryItemDTO>;
}

export interface TeacherStudentDTO {
  user_id: string;
  display_name: string;
  submitted_attempt_count: number;
  latest_attempt_id: string | null;
  latest_report_id: string | null;
}
```
