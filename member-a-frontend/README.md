# 成员 A · LearnMate 前端交付

本目录已整合原有完整前端，并适配组仓库当前 B/C/D 协议。默认入口调用真实 B 后端；完整示例环境独立保留，不会在后端失败时自动切换示例。

## 启动真实流程

在组仓库根目录准备 Python 3.11+ 和 Node >=22.12：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe scripts/start_services.py
```

另开终端：

```powershell
cd member-a-frontend
npm ci
npm run dev
```

访问 http://127.0.0.1:5173/#/login 。本地起步服务账号 student / demo12345、teacher / demo12345；这些是公开教学样例，禁止用于正式生产。页面不显示或预填密码。

当前机器没有 npm 启动器，可以在 A 目录使用：

```powershell
node ../../code/.tools/package/bin/npm-cli.js ci
node ../../code/.tools/package/bin/npm-cli.js run dev
```

该本机替代路径不随组仓库交付；其他同学使用标准 npm。

## 模式与功能边界

| 命令               | 端口 | 用途                                                                            |
| ------------------ | ---- | ------------------------------------------------------------------------------- |
| npm run dev        | 5173 | 组仓库 group-v0：真实登录、单选测验、报告、引用、历史、复测、教师概况和文本导入 |
| npm run dev:mock   | 5175 | 完整功能示例：原有学生/教师页面、多选、图表、维护和文件上传模拟                 |
| npm run dev:debug  | 5176 | 完整示例的本地故障与重置控制，不对外发布                                        |
| npm run dev:real   | 5174 | full-v1 扩展协议开发入口；当前 B 尚未实现，不能作为现有后端的启动入口           |
| npm run build      | —    | 类型检查并构建组仓库真实入口，输出 dist/group                                   |
| npm run preview    | 4175 | 预览组接口构建；B/C/D 仍需运行                                                  |
| npm run build:mock | —    | 构建完整示例，输出 dist/mock                                                    |

完整 mock 账号 demo_student_a / Demo123!、demo_student_b / Demo123!、demo_teacher / Demo123! 与真实骨架账号不同。不同端口、协议使用独立会话/草稿。默认组入口不依赖缺失的 /auth/me，也不伪造令牌过期时间。

可覆盖 .env.group.local 设置 BACKEND_PROXY_TARGET，默认 http://127.0.0.1:8000；API 请求通过同源 /api/v1 代理。VITE_* 会进入浏览器，严禁放秘密。旧骨架的 VITE_USE_MOCK 已不再用于模式选择。

## 当前实现

- 按 B 的数值 code=0、小写 bearer、用户和课程字段进行运行时校验。
- 从课程题目接口取题；一次 POST /attempts 提交，使用真实成绩与内嵌报告。
- 会话内保存草稿、提交键和锁定答案；刷新后恢复，相同提交重试复用 Idempotency-Key。用户退出清除草稿。题目内容变化则不沿用旧草稿；遇到不确定提交先核对历史。
- 诊断不可用仍显示已保存成绩；支持刷新和 POST /attempts/{id}/report 重新生成。不虚构异步进度。
- 解析 Unix 秒时间；比较比例转换为百分点；保留空值和证据不足。
- 历史当前由后端整表返回，前端每页显示 10 条；大数据场景需 B 提供服务端分页。
- 教师可查看概况、导入课程文本到 C。重复网络重试保持资源/文档 ID，但后端尚未提供导入幂等契约，不能保证并发重复提交语义。
- 服务端退出撤销会话；401 清会话并回登录。服务错误不直接回显路径、堆栈或原始字段。
- 普通页面隐藏内部 ID、模式枚举和原始执行轨迹；规则模板、非 LLM 的分析来源如实标识。

当前 B 不提供完整课程/题库 CRUD、学生报告管理、文件上传下载、独立任务和个性化练习组卷。真实入口不会显示无效按钮；这些已有前端功能保留在完整示例中，待扩展接口确认后接入。文本导入不会自动更新 B 的硬编码资源推荐目录，需 B/C 后续完善。

## 验证

```powershell
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
npm run check:group-artifacts
npx playwright install chromium
npm run test:e2e:group
npm run test:e2e
npm run test:e2e:showcase
```

真实浏览器测试需根目录 .venv 的 Python 依赖，可用 GROUP_PYTHON 指定 Python。它启动临时数据库和索引的 B/C/D（19280—19282）与 Vite（5183），不会连接日常数据库。测试输出按模式分目录；完整示例测试使用 5180/5182。

## 目录与交接

- src/group：当前组协议对应的真实入口、页面、校验和 API。
- src/full-main.ts、src/views 等：原有完整功能与 full-v1 扩展接口。
- docs/group-integration.md：当前实际接口、前端适配及后端待办，优先用于本次联调。
- docs/frontend/backend-api-alignment.md：完整功能扩展提案，不是现有 B 已全部提供的协议。
- docs/group-baseline：组长原始骨架文档存档，内含尚未适配时的状态，仅供历史参考。
- docs/testing/frontend/group-adaptation-results.md：本轮验证记录。

依赖统一使用 npm 和 package-lock.json；不保留过期 pnpm 锁文件。node_modules、dist、本地环境文件和测试输出均不提交。完整示例截图仅含原创样例；公开仓库需自行复核截图内容。
