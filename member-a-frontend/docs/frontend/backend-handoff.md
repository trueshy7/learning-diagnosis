> 当前默认组仓库入口使用 group-v0，见 [实际联调文档](../group-integration.md)。本文保留为 full-v1 扩展协议提案，不能视为当前 B 已实现。

# B C D 接入与待确认矩阵

交接主文档：[完整前后端接口对齐文档 v1.1](backend-api-alignment.md)。覆盖37接口、34个实际DTO，以及错误、幂等、任务、权限、文件、版本和联调门禁。先确认主文档，再填写下面的待确认矩阵。

状态均为“前端草案已实现；正式服务待确认/待联调”。尚未收到队友评审，不记录虚假确认。

| 链路               | 调用页面/材料             | 所需确认                                                    | 负责人 | 正式状态 |
| ------------------ | ------------------------- | ----------------------------------------------------------- | ------ | -------- |
| 登录、me、退出     | LoginView/auth store      | Bearer或Cookie、过期/退出、部署源/CORS                      | B      | 待确认   |
| 课程与知识点       | Courses/Course/教师维护   | ID、默认课程获取、空列表、软停用冲突                        | B      | 待确认   |
| 创建/提交/查询测验 | AttemptView               | 快照、题型、计分明细、创建/提交幂等、答案开放边界           | B      | 待联调   |
| 诊断任务           | DiagnosisView/TaskPoller  | 状态、progress、超时、can_retry、任务完成后报告可查询       | B/D    | 待联调   |
| 报告与历史         | ReportView/HistoryView    | 归属、分页排序、null、版本、成绩一致性                      | B/D    | 待联调   |
| 来源与文件         | EvidenceList/ResourceView | ID映射、章节/页码、Blob或授权URL、410、旧引用快照           | B/C    | 待联调   |
| 推荐与练习         | RecommendationList        | priority、合法resource/question ID、用时、空态              | D/B    | 待联调   |
| 复测比较           | ComparisonPanel           | baseline、两次覆盖、规则/难度、百分点单位、整体与局部可比性 | D/B    | 待联调   |
| 教师题库           | QuestionsManage           | client_key/option_id映射、选项变化、历史快照不可变          | B      | 待确认   |
| 上传与资料         | ResourcesManage           | multipart字段、10MiB限制、支持格式、任务恢复与取消语义      | B/C    | 待联调   |
| 教师学生报告       | OverviewView/专用路由     | 授权课程范围、学生查询、禁止任意越权                        | B      | 待联调   |

D另确认mastery_status四状态、minimum题量、correct_rate/mastery_score null语义、rule_version、检索空和模板降级区别。可提供真实agent_steps时才展示，不由前端补造轨迹。

接入步骤：获取OpenAPI → 逐项对照草案 → 修改.env.real.local → 登录与课程 → 测验计分 → 任务报告 → 引用推荐 → 复测历史 → 教师上传。结构不同集中改contracts/endpoints/mappers并记录差异，更新fixture与契约测试。

每步记录脱敏Network请求、request_id、后端/规则/索引版本和界面值。断开真实API验证明确失败，禁止隐藏mock回退。全组最后共同跑真实正常模型闭环与真实降级场景，此前不宣称真实集成通过。
