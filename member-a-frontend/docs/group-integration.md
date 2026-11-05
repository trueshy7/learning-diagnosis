# 当前组仓库前后端联调协议

日期：2026-11-05；协议标识 group-v0；默认 `npm run dev` 使用本文协议。依据为 B 实际源码，不要求 B 直接兼容完整功能扩展草案。

## 模块边界

A 仅访问 B 的 `/api/v1`，B 调用 D，D 经 HTTP 调 C。默认前端 5173 以 Vite 同源代理转发至 B 的 8000；C/D 默认 8001/8002。不得在前端存放模型密钥、调用 C/D 内部路由或重算正式计分。

成功响应 `{code:0,message:"ok",data:...,request_id:"..."}`，失败使用非零数值 code 与 HTTP 错误码。登录后带 `Authorization: Bearer <access_token>`。用户身份来自 B，路由隐藏不替代 B 授权。错误追踪保留在 ApiError.requestId/浏览器网络响应；普通界面显示安全中文，不暴露堆栈和路径。

## 当前页面实际调用

| 方法 | 路径                   | 请求或说明                                                                                                            |
| ---- | ---------------------- | --------------------------------------------------------------------------------------------------------------------- |
| POST | /auth/login            | `{username,password}`；返回 `{access_token,token_type:"bearer",user:{id,username,role}}`                              |
| POST | /auth/logout           | 返回 `{logged_out:true}`，服务端撤销后清理本机会话；网络失败仍清本机但提示撤销未确认                                  |
| GET  | /courses               | `[{id,name,description}]`                                                                                             |
| GET  | /courses/:id/questions | `{questions:[{id,stem,kind:"single",options:[{id,text}],knowledge_point_ids}]}`；禁止标准答案字段                     |
| POST | /attempts              | `{course_id,answers:[{question_id,selected_option_ids}],baseline_attempt_id?}`，携带 Idempotency-Key，返回 Attempt    |
| GET  | /attempts              | 当前用户完整 Attempt 数组；前端每 10 条分页展示                                                                       |
| GET  | /attempts/:id          | 本人 Attempt；他人记录应 403，不存在 404                                                                              |
| POST | /attempts/:id/report   | 同步请求重新生成报告并返回 Attempt，不伪装成任务轮询                                                                  |
| GET  | /teacher/overview      | `{user_count,question_count,attempt_count,resource_count}`                                                            |
| POST | /teacher/resources     | `{resource_id,document_id,course_id,title,text,knowledge_point_ids,source}`；返回至少 `{chunks}`，其余 C 元数据可保留 |

后端无 `/auth/me`，A 不额外请求。服务器校验令牌后出现 401 时会清理当前登录和草稿、转回登录页。B 未返回 expires_at，不伪造自动刷新或过期时间。

## 成绩与报告

Attempt 的实际字段见 `src/group/types/api.ts`，运行时校验见 `src/group/services/contracts.ts`：

- `id,course_id,created_at,baseline_attempt_id,status,score,max_score,percentage,report,ai_status,ai_message`。
- created_at 是 Unix 秒，显示时乘 1000，按 Asia/Shanghai 展示；percentage 为 0—100，接受两位小数舍入。
- status=completed 表示计分完成，不代表诊断完成。report 可 null；ai_status 为 processing/unavailable/disabled 时仍显示已保存成绩。
- report.attempt_id 必须等于 Attempt.id；completed 的 ai_status 应包含完整报告。
- 报告采用 mode=rule_template_demo，显示“规则与模板分析 · 未调用大语言模型”。原始 trace、ID 和模式枚举不公开显示；引用文本和真实出处保持原意。
- accuracy、before_accuracy、after_accuracy、delta 都是比例。比较时 delta 乘 100 显示百分点；null 不换成 0。不得自行创建不存在的报告版本、引用 URL 或可比结果。
- 少于 3 道有效题是证据不足；needs_practice 对应“需要巩固”。分类由 D 输出，A 不在真实模式重算。
- 引用 location 兼容字符串或位置对象，source 是文字；缺少授权全文接口时仅显示返回片段，不猜 URL。

## 草稿、幂等与恢复

以用户、课程、基线隔离 sessionStorage 草稿。首次提交锁定答案和 Idempotency-Key；保存题目内容签名。网络失败后刷新可恢复原提交意图；重试使用同键同体，不创建第二条记录。用户退出或切换账号清理组协议草稿。

若题目内容变化、存储损坏或本地选项不合法，旧草稿不恢复。B 目前没有服务端快照和按提交键查询接口，因此遇到不确定提交且草稿无法恢复时，应先从历史核对；不能承诺任意浏览器关闭/题库变化后都可准确恢复。

B 当前顺序重试可复用记录；并发同键事务冲突处理仍需 B 完善。前端按钮限制只能减少重复操作，不能替代数据库唯一约束和事务。

## 教师文本导入边界

A 按课程题目返回的知识点 ID 提供选择，当前已确认栈和队列。资料与文档 ID 由本次表单创建，失败重试保留。成功后显示 C 返回的分块数量。

文本导入成功不代表已写入 B 的硬编码 RESOURCES、教师计数或 D 推荐目录；课程后台需进一步统一资源存储与索引。该接口不是 PDF/TXT 文件上传，无文件上传按钮。并发导入幂等、服务端内容校验、索引权限和生产内部服务认证由 B/C 继续完善。

## 后端配合顺序

1. 保持本轮 group-v0 登录、课程、提交、报告、来源和比较字段兼容；改字段先更新一组请求响应样例，并通知 A。
2. 补课程/知识点/题库/资源持久化、迁移与课程权限，替换硬编码目录；补多选评分。
3. 协商服务端测验快照、并发幂等、服务端分页和上传/资料访问；不要只增加空字段骗过前端校验。
4. 再评审 `frontend/backend-api-alignment.md` 的 full-v1 完整功能方案：独立任务/报告、推荐练习、完整教师维护、学生授权报告和历史版本资料。
5. C/D 的真实向量检索、模型解释、效果与安全验收另行完成，本次规则与关键词联调不代表上述能力完成。

## 发布与验证

开发用 `npm run dev`，构建用 `npm run build`，产物 `dist/group`；公开部署需要同源 `/api/v1` 反向代理和 HTTPS。组入口使用 hash 路由，无需为前端路由配置 history fallback；API 错误不得回退为 HTML。完整示例入口仍使用原 history 路由，部署要求不同。

`npm run test:e2e:group` 使用临时端口、临时数据库和索引启动实际 B/C/D，不复用日常数据。日常服务无需同时启动，端口已占用时测试拒绝复用。GROUP_PYTHON 可指定安装依赖的 Python。

本轮结果见 [适配验证记录](testing/frontend/group-adaptation-results.md)。原组长骨架文档保存在 `group-baseline`，其中未实现描述与旧开关仅作历史参考。
