# 必做需求覆盖矩阵

本表区分前端模拟验证和正式服务联调。最终实际自动化结果以actual-results为准；手工复核状态见manual-cases。

| 需求                      | 代码入口（相对frontend/src）              | 验证入口                                      | mock状态                            | real状态       |
| ------------------------- | ----------------------------------------- | --------------------------------------------- | ----------------------------------- | -------------- |
| A1 双角色流程、七类页面   | router/index.ts、views、styles/main.css   | page-map、E01/E17/E25                         | 已实现，最终自动化通过              | 待联调         |
| A2 登录/路由/会话/403/404 | stores/auth.ts、api/client.ts、router     | U08/U09、E02/E16/E24                          | 已实现，最终自动化通过              | 待联调         |
| A3 创建/单多选/未答       | AttemptView、QuestionCard、services       | E03/E04/U06                                   | 已实现，最终自动化通过              | 待联调         |
| A3 草稿/刷新/提交幂等恢复 | composables/draft、AttemptView            | U07/U18/U22、E05—E07                          | 已实现，最终自动化通过              | 待联调         |
| A4 成绩与诊断语义         | ScoreCard、KnowledgeTable、contracts      | U01/U04/U13/U14、E08/E09                      | 已实现，最终自动化通过              | 待联调         |
| A4 引用与来源             | EvidenceList、ResourceView                | E10/E22/U17                                   | 已实现，最终自动化通过              | 待联调         |
| A5 推荐练习、固定复测     | RecommendationList、ComparisonPanel       | E11—E14/U15                                   | 已实现，最终自动化通过              | 待联调         |
| A5 历史及完整报告         | HistoryView、ReportView                   | E01/E13/E24                                   | 已实现，最终自动化通过              | 待联调         |
| A6 教师课程/知识点/题库   | views/teacher                             | U16、E17/E18                                  | 已实现，最终自动化通过              | 待联调         |
| A6 资料关联/上传/任务恢复 | ResourcesManage、api/services             | E19/E20/U17                                   | 已实现，最终自动化通过              | 待联调         |
| A6 学生概况与专用报告     | OverviewView、teacherReport endpoint      | E21/E16                                       | 已实现，最终自动化通过              | 待联调         |
| A7 有限轮询/重试/异常     | useTaskPolling、PageState、api/client     | U03/U10—U12、E15/E23                          | 已实现，最终自动化通过              | 待联调         |
| A7 实际HTTP与mock隔离     | main.ts、mocks、contracts/mappers         | build:real/check:real-artifacts/test:e2e:real | 真实适配器已实现，隔离/契约检查通过 | 无正式后端     |
| A8 双尺寸/长文本/截图     | styles/main.css、tests/e2e                | E25、screenshots                              | 已实现，最终自动化通过              | 待真实环境复验 |
| A8 文档与贡献材料         | docs/frontend、docs/testing、docs/reports | 手工矩阵、使用/演示脚本                       | 已提供，人工待复核                  | 待补真实证据   |

64题、20资料、10记录是可交互模拟基线，check:fixtures检查数值、关联、引用、baseline和快照。不代替C检索Hit@5评测或D真实模型质量评估。
