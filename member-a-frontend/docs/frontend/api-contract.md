> 当前默认组仓库入口使用 group-v0，见 [实际联调文档](../group-integration.md)。本文保留为 full-v1 扩展协议提案，不能视为当前 B 已实现。

# 前端接口速查

**后端新实现请以 [完整接口对齐文档 v1.1](backend-api-alignment.md) 为准。** 本文保留首版速查结构；新文档补充了完整DTO字段、缓存来源、历史资源版本、精度、权限与事务语义，优先级高于旧描述。

本文件描述本次实际前端与模拟服务采用的契约，尚未得到 B/C/D 确认。类型及运行时校验的完整定义在 `frontend/src/api/contracts/index.ts`，路径集中在 `frontend/src/api/endpoints.ts`，调用在 services，适配在 mappers。不得把模拟规则当作正式算法要求。

## 基础协议

基址 `/api/v1`；不透明字符串 ID；UTC ISO8601（带Z）时间，显示 Asia/Shanghai。成功200/201/202，code=OK；错误使用对应HTTP状态和业务码。返回结构：

```json
{
  "code": "OK",
  "message": "成功",
  "data": {},
  "request_id": "server-generated-id"
}
```

错误data=null，可选errors=[{field,message}]。缺服务request_id时，客户端保留前缀local:的本地标识，不冒充服务追踪ID。FastAPI默认422 detail数组有明确兼容映射。分页为items、total、page（从1开始）、page_size（默认10，上限50）。未测数据null；实际0是合法值。

登录之外带Authorization: Bearer token。本草案无刷新令牌。401清当前会话，403保留；登录INVALID_CREDENTIALS只显示表单错误。退出请求失败仍清本地会话。

## 已实现路径

| 方法       | 路径（省略基址）                    | 输入                                                    | data                                             |
| ---------- | ----------------------------------- | ------------------------------------------------------- | ------------------------------------------------ |
| POST       | /auth/login                         | username,password                                       | access_token,token_type=Bearer,expires_at,user   |
| GET        | /auth/me                            | Bearer                                                  | User                                             |
| POST       | /auth/logout                        | Bearer                                                  | null                                             |
| GET        | /courses                            | 无                                                      | Course[]                                         |
| GET        | /courses/:id                        | 课程ID                                                  | Course                                           |
| GET        | /courses/:id/knowledge-points       | 课程ID                                                  | KnowledgePoint[]                                 |
| POST       | /attempts                           | CreateAttempt                                           | Attempt，201                                     |
| GET        | /attempts                           | course_id,kind,page,page_size                           | Page<History>                                    |
| GET        | /attempts/:id                       | 本人ID                                                  | Attempt                                          |
| POST       | /attempts/:id/submit                | SubmitAttempt，Idempotency-Key                          | attempt_id,submitted_at,result,diagnosis_task_id |
| GET        | /attempts/:id/result                | 本人ID                                                  | AttemptResult                                    |
| GET        | /tasks/:id                          | 本人诊断或教师文档任务                                  | Task                                             |
| POST       | /tasks/:id/retry                    | {}，Idempotency-Key                                     | Task，202                                        |
| GET        | /reports                            | course_id,kind,page,page_size                           | Page<History>                                    |
| GET        | /reports/:id                        | 本人报告                                                | Report                                           |
| GET        | /reports/:id/recommendations        | 本人报告                                                | report_id,attempt_id,recommendations,actions     |
| GET        | /reports/:id/comparison             | 本人报告                                                | Comparison或null                                 |
| GET        | /resources/:id                      | 可选document_id,chunk_id                                | ResourceDetail                                   |
| GET        | /resources/:id/file                 | Bearer                                                  | 原文件二进制；失败仍返回JSON envelope            |
| GET        | /teacher/overview                   | course_id                                               | Overview                                         |
| GET        | /teacher/students                   | course_id,q,page,page_size                              | Page<TeacherStudent>                             |
| GET        | /teacher/students/:uid/attempts     | course_id,page,page_size                                | Page<History>                                    |
| GET        | /teacher/students/:uid/reports/:rid | 学生与报告归属必须一致                                  | Report                                           |
| PATCH      | /teacher/courses/:id                | title,description                                       | Course                                           |
| GET        | /teacher/knowledge-points           | course_id,q,active,page,page_size                       | Page<KnowledgePoint>                             |
| POST/PATCH | /teacher/knowledge-points[/:id]     | KnowledgeWrite                                          | KnowledgePoint                                   |
| GET        | /teacher/questions                  | course_id,type,knowledge_point_id,active,page,page_size | Page<TeacherQuestion>                            |
| GET        | /teacher/questions/:id              | 教师身份                                                | TeacherQuestion                                  |
| POST/PATCH | /teacher/questions[/:id]            | QuestionWrite                                           | TeacherQuestion                                  |
| GET        | /teacher/resources                  | course_id,kind,knowledge_point_id,active,page,page_size | Page<TeacherResourceListItem>                    |
| GET        | /teacher/resources/:id              | 教师元数据读取，包含停用资源以便恢复                    | ResourceDetail                                   |
| POST/PATCH | /teacher/resources[/:id]            | ResourceWrite                                           | ResourceDetail                                   |
| POST       | /teacher/documents                  | FormData                                                | {document,task}，202                             |
| GET        | /teacher/documents/:id              | 教师身份                                                | Document                                         |

停用使用PATCH active=false，不实现物理删除。学生接口不能返回correct_option_ids、解析或教师临时client_key。教师报告读取用专用路径。

## 主要结构

Course包含course_id,title,description,knowledge_points,latest_attempt_id,active_attempt_id,latest_report_id。KnowledgePoint包含knowledge_point_id,course_id,name,description,sort_order,active。

StudentQuestion包含question_id,type(single_choice/multiple_choice),stem,options[{option_id,label,text}],knowledge_point_ids,difficulty(easy/medium/hard)。学生schema对泄露字段拒绝，而不只是UI隐藏。TeacherQuestion增加course_id,correct_option_ids,explanation,active,version。

Attempt包含attempt_id,user_id,course_id,kind(initial/practice/retest),baseline_attempt_id,source_report_id,status(in_progress/submitted),snapshot_version,created_at,submitted_at,questions,result,diagnosis_task_id,report_id。result包含attempt_id,score,graded_answers[{question_id,selected_option_ids,is_correct}],rule_version。学生提交后仍不返回标准答案。

Score包含correct_count,total_count,raw_score,max_score,percentage（0—100）。掌握度/正确率是0—1，不混用。总分与明细数量/正误一致性进行校验，知识点题数不求和冒充总题数。

Task包含task_id,kind(diagnosis/document_ingestion),status(queued/running/completed/failed),attempt_id,document_id,report_id,progress(0—1或null),current_step,error_code,error_message,can_retry,retry_count,created_at,updated_at。完成诊断必须已有可查询report_id；完成文档无需报告ID。

Report包含归属标识、generated_at、report/rule/data_version、source_mode(mock/backend)、explanation_mode(llm/rule_template/cached)、is_degraded、degraded_reasons、retrieval_status(available/empty/failed/not_requested)、score、summary、knowledge_points、evidences、recommendations、comparison、agent_steps、actions。当前模拟报告不用cached或伪造智能体轨迹。

知识点项包含名称、correct_count,question_count,correct_rate,mastery_score,mastery_status(weak/consolidating/mastered/insufficient_evidence),coverage_reason(not_tested/too_few_questions/null),wrong_question_ids,explanation,evidence_ids。无题量时两个比例都null；覆盖不足时mastery_score=null，可保留2/2的correct_rate=1。正式前端不按固定阈值重新诊断。

Evidence包含evidence_id,resource_id,document_id,chunk_id,document_title,knowledge_point_ids,text,location{page_start,page_end,section},source_label,resource_version,availability(available/removed/unknown)。引用ID必须属于当前报告。文本章节实际存在，不把相关度当可信概率。

Recommendation包含recommendation_id,knowledge_point_id,priority,reason,next_step,estimated_minutes,evidence_ids,resources,practice_questions[{question_id,title,type}]。服务顺序保留，空集合有空态；ID必须可回查。

Comparison包含baseline/current_attempt_id、两次rule_version、overall_comparable、overall_reason、overall_delta_percentage_points、knowledge_points。每点包含comparable,reason、两次correct_rate/question_count、delta_percentage_points,difficulty_note。不可比差值null且有原因；部分点可比不等于整卷可比。

## 写入与幂等

创建示例：

```json
{
  "course_id": "course-ds",
  "kind": "retest",
  "client_request_id": "one-create-intent",
  "baseline_attempt_id": "attempt-a-001",
  "source_report_id": "report-a-001"
}
```

initial不指定题目；practice仅使用source_report中的合法question_ids；retest由服务选题，baseline必须对应source_report本人同课程已提交测验。相同创建意图重试返回同一attempt；同标识不同内容409。

提交：{snapshot_version,answers:[{question_id,selected_option_ids}]}，每道且仅一次，空答[]；Idempotency-Key在待确认期间不变。相同规范化答案返回原结果和任务；不同答案409，不覆盖成绩。响应丢失后先GET同attempt，不能直接新建。多选数组顺序不改变语义。

QuestionWrite：course_id,type,stem,options[{option_id:null或已有ID,client_key,label,text}],correct_option_keys,knowledge_point_ids,difficulty,explanation,active。答案引用稳定client_key，服务分配真实option_id并返回correct_option_ids。单选恰好1答案，多选>=2；2—6选项；至少1有效知识点。

ResourceWrite：course_id,title,description,kind,note正文text_content或external_url,knowledge_point_ids,difficulty,active。POST仅note/external，document由上传创建，PATCH文档只改元数据。链接只允许http/https。

上传FormData字段：course_id,title,knowledge_point_ids（JSON字符串数组）,file。默认10MiB，支持TXT/MD/PDF。返回受理不等于处理完成。Document含document_id,resource_id,course_id,filename,size_bytes,content_type,version,task_id,status,error_code,error_message,created_at。资源列表额外返回document_id,ingestion_task_id,error_code,error_message，以便刷新恢复。

长度统一schema：标题1—100，题干1—2000，选项1—500，说明/解析0—3000；可见首尾空白trim。原文正文保留段落。输入失败保留表单。

## 错误码

401 AUTH_REQUIRED/TOKEN_EXPIRED/INVALID_CREDENTIALS；403 FORBIDDEN；404 NOT_FOUND；409 ATTEMPT_ALREADY_SUBMITTED/SNAPSHOT_MISMATCH/TASK_NOT_RETRYABLE/REFERENCE_CONFLICT/DUPLICATE_NAME/ATTEMPT_NOT_SUBMITTED；410 RESOURCE_REMOVED；413 FILE_TOO_LARGE；415 UNSUPPORTED_FILE_TYPE；422 VALIDATION_ERROR/INVALID_OPTIONS/INVALID_BASELINE；500 MOCK_ERROR；未覆盖模拟API返回404 UNIMPLEMENTED_API并可见失败。

客户端自有NETWORK_ERROR、REQUEST_TIMEOUT、REQUEST_CANCELLED、INVALID_RESPONSE，与后端业务码分开。JSON默认10秒，上传60秒；轮询另有次数/总时间限制。

本次实际样例见examples内三份完整报告和测验响应。后续B确认结构后更新本文件、schema、样例和测试，避免页面自行兼容多个含义不同字段。
