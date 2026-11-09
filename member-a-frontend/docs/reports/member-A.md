# 成员 A 前端实现与答辩材料

本人负责范围对应A1—A8：用户流程、Vue界面、接口接入、诊断与证据展示、推荐和复测、教师维护、前端异常与验证。当前实现由Codex辅助完成，成员A应阅读代码、复验并理解关键设计；未伪造本人独立手写、Git提交、队友审查或教师认可。

## 关键代码入口

- frontend/src/router/index.ts：页面范围与角色守卫。
- frontend/src/api/client.ts：Axios、envelope、错误、取消、会话generation。
- frontend/src/api/contracts/index.ts：DTO与Zod、表单及报告不变量。
- frontend/src/views/student/AttemptView.vue：作答、确认、提交意图、响应丢失恢复。
- frontend/src/composables/draft.ts：用户/课程/测验/快照草稿隔离。
- frontend/src/composables/useTaskPolling.ts：串行、有上限、可取消的任务查询。
- frontend/src/components/reports：成绩、知识点图表/表格、引用、推荐和对比。
- frontend/src/views/teacher：教师维护、授权学生报告、上传与任务恢复。
- frontend/src/mocks：隔离HTTP模拟、事务仓储、原创数据；不属于正式算法。

## 可解释的设计

页面不重算正式评分或诊断，数据先运行时校验再展示。2/2保留100%正确率但状态为证据不足，图表不绘掌握柱；真实0分、未覆盖与加载失败分开。引用保存原片段，来源失效不删历史事实。复测绑定当前报告对应baseline，不默认最新记录。

提交响应丢失后查询同attempt，不重新创建记录；只有服务确认仍未提交才允许编辑或用原key/内容重试。有限轮询在终态、错误、切页和退出停止，上限不伪造成失败。用户会话变化用generation取消并拒绝迟到结果。

## 典型修复

浏览器测试发现刷新时auth/me可能在App挂载前返回401，单靠组件事件监听会丢失过期原因；改为会话过期标识配合路由query，并在成功登录后清理。教师筛选增加明确可访问名称；测试在导航完成后读取attempt地址。真实产物检查曾发现启动提示中的演示数据库名称，移除提示中的实现细节并保持严格扫描。

## 验证与贡献证据

真实命令和最终统计见docs/testing/frontend/actual-results.md，需求映射见requirements-matrix.md。截图为真实浏览器运行的模拟页面，手工复核见manual-cases，未执行项标待执行。当前目录无Git仓库，因此不存在可引用的本次Git提交号。

## 后续协作与限制

接口为草案v1，尚未获B/C/D确认。真实后端、数据库事务、正式权限安全、检索质量、真实模型与智能体质量均待相应负责人交付后联调。模拟PDF不做解析/OCR/向量索引。仅以单课程和两类角色验证，未扩展知识图谱、多课程、聊天机器人或复杂移动端适配。

答辩重点：演示真实选项改变模拟成绩、2/2不足、引用来源、固定baseline、教师保存和异常恢复；清楚说明mock通过与全组真实验收的区别。前端检查通过不代表系统已被证明提升学生成绩。
