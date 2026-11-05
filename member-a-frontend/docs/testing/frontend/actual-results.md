# 实际执行结果

最新迁入组仓库及真实 B/C/D 验证见 [2026-11-05 适配记录](group-adaptation-results.md)。以下为迁入前历史记录。

最新补充见 [2026-10-23 对外展示复核](review-2026-10-23.md)。下文保留 2026-10-22 首轮执行记录，不代表当前用例总数。

日期：2026-10-22，Asia/Shanghai。工作目录：`D:\a_workplace\learnmate\code\frontend`。执行者：Codex 自动化。人工复核仍待执行，不把 E2E 通过冒充人工检查。

## 环境与版本

Windows；Node v24.19.0；官方 npm 12.2.1 本地副本；Chromium 156.0.8078.4（Playwright chromium v1248）。

锁定版本：Vue 3.5.44、Vue Router 4.6.4、Pinia 3.0.4、Vite 7.3.7、TypeScript 5.9.3、Element Plus 2.14.7、ECharts 6.1.0、Axios 1.20.0、Zod 4.6.7、MSW 2.15.0、idb 8.0.4、Vitest 3.2.7、Playwright 1.64.1。完整传递依赖在 package-lock.json。

本机无 npm 启动器，以下 npm 命令均实际通过 `node ../.tools/package/bin/npm-cli.js ...` 执行，不依赖全局安装。有标准 npm 的机器使用普通命令即可。

## 最终命令结果

| 命令                                                       | 退出码 | 实际结果                                                      |
| ---------------------------------------------------------- | ------ | ------------------------------------------------------------- |
| npm install --no-fund --no-audit                           | 0      | 首次安装366包并生成锁文件                                     |
| npm install-scripts approve msw esbuild                    | 0      | 明确批准两个依赖的必要安装脚本，写入package.json              |
| node node_modules/msw/cli/index.js init public --save      | 0      | 生成官方worker                                                |
| npm ci --no-fund --no-audit                                | 0      | 按锁文件重新安装366包，可复现                                 |
| npm run typecheck                                          | 0      | strict TypeScript与Vue模板检查通过                            |
| npm run lint                                               | 0      | 源码及测试静态检查通过                                        |
| npm run format:check                                       | 0      | 格式检查通过                                                  |
| npm run check:fixtures                                     | 0      | 8知识点、64题、16多选、20独立资料、10记录；固定成绩与关联一致 |
| npm run test:unit                                          | 0      | 6文件、56测试通过，0失败、0跳过；最终执行19:50                |
| npm run build:mock                                         | 0      | 输出dist/mock，含隔离模拟模块和worker                         |
| npm run build:real                                         | 0      | 输出dist/real，不含模拟代码和worker                           |
| npm run check:real-artifacts                               | 0      | 扫描21个真实文件，无演示账号、答案、模拟仓储和控制入口        |
| node node_modules/@playwright/test/cli.js install chromium | 0      | 安装Chromium、headless shell及配套组件                        |
| npm run test:e2e                                           | 0      | 最终14组通过、0失败、0跳过，组合覆盖E01—E25，约1.1分钟        |
| npm run test:e2e:real                                      | 0      | 2组通过、0失败、0跳过；真实构建隔离和真实适配器契约检查       |

最后一轮单元测试增加了教师停用资源元数据读取及恢复检查，不改变应用代码。默认build与build:real采用相同Vite真实构建命令，避免依赖嵌套的全局npm命令。

真实模式第一项测试确实没有B服务，预览代理返回ECONNREFUSED 127.0.0.1:8000；页面明确失败且没有回落演示数据，属于预期验证。第二项使用仅位于tests的Playwright网络替身验证/api/v1地址、Bearer、me角色和DTO解析，不能称为真实B/C/D集成通过。

## 浏览器与截图

Chromium实际操作学生与教师完整流程，包含新作答、单多选、空答确认、刷新恢复、幂等提交、响应丢失恢复、推荐练习、固定baseline复测、来源阅读/410、教师持久化、文件上传/失败/取消、权限、会话与长文本。

在1366×768和1920×1080检查长内容，断言documentElement.scrollWidth不超过innerWidth。16张运行截图在screenshots目录，包括登录、课程、测验、诊断、引用展开、推荐、复测比较、教师题库、上传处理和异常。截图等待页面挂载/数据展示后重新采集，保留模拟标识；已目视检查登录、课程和诊断代表截图。未声称其他浏览器也通过。

## 发现与修复记录

1. 初始类型检查发现Vue模板直接引用window/crypto不被模板类型识别，改用脚本方法；ESLint对SFC使用vue-tsc负责标识类型校验，保留其他静态规则。
2. 第一轮浏览器启动受沙箱本机HTTP EACCES限制，未执行用例；仅清理本次测试进程后，以允许本机网络的权限运行，不记为功能通过。
3. 首轮模拟浏览器9通过、5失败。真实缺陷：刷新时/me的401早于App监听，过期提示丢失；增加过期标识与路由传递，成功登录后清理，复验通过。
4. 复验发现教师资源表单能在课程尚未取得时提前打开，course_id为空；课程就绪前禁用新建入口，复验通过。
5. 浏览器历史恢复增加pageshow persisted校验：隐藏冻结私有DOM并重新加载，防止旧账号页面从后退缓存恢复；退出后先等待登录页，再验证后退仍受保护。
6. 测试导航原先在路由完成前读取attempt地址，筛选定位不够明确；改为等待URL/可见状态，并提供筛选控件明确可访问名称，保留原数值和权限断言。
7. 严格产物检查发现真实启动错误提示中残留演示仓储名称；从用户提示移除实现细节，真实构建21文件扫描通过，未放宽检查。
8. 轮询总时限增加独立deadline中断慢请求，并有测试验证。任务重试同key不重复计数；教师可通过专用接口读取停用资源元数据并恢复。

## 仍需后续执行

人工检查矩阵由成员A及组员实际复核；Edge/Firefox未执行。B/C/D接口确认、真实权限/数据库事务、真实资料解析检索、真实模型/智能体和全组闭环均待联调。模拟PDF仅保存文件并模拟状态，不做OCR或索引。未执行付费模型或发布公网。

安装提示whatwg-encoding和ESLint 9弃用；当前兼容组合已锁定并通过检查，未来升级需评估插件兼容。构建有Zod源注释PURE位置的Rollup提示，注释被移除，构建成功，无隐藏失败。
