# 前端架构与状态管理

2026-10-23复查更新：默认mock展示与本地debug分离，只有显式VITE_SHOW_DEV_TOOLS=true的本地mock开发可显示控制；生产构建与真实模式禁止该开关。普通页面使用统一安全中文提示，调试信息按config.debug隔离。完整接口以backend-api-alignment.md为准。

Vue 3 Composition API、strict TypeScript、Vue Router 4、Pinia、Element Plus、ECharts。请求只经过 api/services → api/client 的 Axios → HTTP。页面不导入模拟数据。DTO 与运行时 Zod schema 位于 `frontend/src/api/contracts/index.ts`，字段转换和请求ID匹配在 mappers。

## 真实与模拟边界

main.ts 使用构建期可消除的条件动态加载 mocks/browser，并等待 IndexedDB 初始化与 MSW setupWorker 启动后才挂载应用。Node 单元测试的 setupServer 复用同一 handlers。模拟模块保存原创题库答案、演示账号与规则实现；真实构建不导入这些模块，构建插件移除 public 中的 worker。产物检查遍历真实输出验证敏感演示标识未泄漏。

MSW 只替换 HTTP 边界，页面、服务、DTO 一致。真实接口失败绝不回退到样例。模拟控制对象与场景面板仅存在于模拟 chunk。

## 身份与竞态

令牌在 sessionStorage，Pinia 只保存经 /auth/me 验证的用户。bootstrap 共享一次 Promise。401 清理令牌和私有草稿，通过单一事件回登录；错误口令只在登录表单显示；403 不清会话。每次会话清理递增 generation，取消在途请求；客户端和 useLoad 均拒绝旧会话迟到结果。路由参数变化后 useLoad 序号阻止旧数据写回。

## 测验与提交

草稿键包含用户、课程、attempt 和 snapshot_version，只保存已选 option_id。先 GET 测验确认状态，再恢复合法草稿。已提交与快照不匹配时清理相应草稿。

每次创建意图持有 client_request_id。提交前冻结规范化答案与 Idempotency-Key，保存在当前标签会话。网络失败时进入待确认，查询同一 attempt；已保存就恢复成绩，查询失败保留待确认，仍未提交时允许原内容重试或明确返回编辑。组件不计算正式成绩。

## 模拟持久化

`learning-diagnosis-demo-v1` 中单个 demo-state 仓储包含用户、token、题目、资源、快照、任务、报告、文件 Blob。每次操作在 IndexedDB readwrite 事务中重新读取最新状态后同步变更、提交，避免缓存全库对象反复覆盖。内存实现串行队列，供 Node 测试注入。异常事务回滚并处理 done 拒绝。

任务按持久化 created_at/updated_at 与当前时钟推进，刷新和离页不会丢业务状态。PDF 仅保存 Blob 与模拟状态，不宣称解析或生成索引。

## 轮询与展示

TaskPoller 在上次请求完成后才安排下一次，具备次数及时间上限，任务终态、错误、stop、任务切换和卸载均停止。停止会中断请求，序号隔离迟到响应。上限只显示“仍在处理”，不伪造服务失败。

知识点掌握度只有非 null 且非覆盖不足时进入图表。2/2 可在表格显示100%正确率，掌握度图不显示。实际0%仍为有效值。图表与表格同源，ResizeObserver 调整尺寸，卸载 dispose；图表故障仍可阅读表格。对比只展示接口提供的 comparable 与百分点，不在 mapper 重算诊断阈值。

## 安全展示

使用 Vue 转义文本和 pre，不执行资料中的 HTML/命令。外链只允许 http/https。授权文件通过 Axios 请求 Blob，JSON 错误先解析，不当作下载。Blob URL 仅在组件生命周期内保存，卸载释放。上传 FormData 不手工拼 boundary。VITE 环境变量中不放密钥。

工具行为核对来源：[MSW 浏览器集成](https://mswjs.io/guides/integrations/browser)、[Playwright 测试服务器](https://playwright.dev/docs/test-webserver)。这些仅支持工具用法，本组业务接口仍为草案。
