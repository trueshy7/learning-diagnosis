# 四人课程设计初始项目

项目题目：基于 RAG 与多智能体协作的个性化学习诊断与推荐系统。

四个目录可分别交给四位成员继续开发，合在一起可以运行一条最小的本地流程：学生登录 → 六道样例题测验 → 确定性计分 → 规则诊断 → C的真实HTTP关键词检索 → 目录资源推荐 → 复测比较。

当前是起步骨架：**使用自编样例、规则诊断和关键词检索；尚未接入真实向量模型或大语言模型。** 各目录的README和开发说明明确列出已实现、占位与接续工作，不代表四份任务书已全部完成。

| 成员 | 目录 | 运行端口 | 本次骨架的可运行内容 |
| --- | --- | --- | --- |
| A | `member-a-frontend` | 5173 | Vue页面、路由、类型、请求封装、样例及真实接口切换 |
| B | `member-b-backend` | 8000 | 登录权限、SQL存储、取题、评分、历史、接入C/D |
| C | `member-c-rag` | 8001 | 文本导入、分段、JSON索引、检索、来源、删除重建 |
| D | `member-d-agents` | 8002 | 规则诊断、固定三阶段编排、推荐、异常处理和复测 |

## 最快联调方式

准备 Python 3.11+ 和 Node.js 22+。在本文件所在目录执行：

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/start_services.py
```

启动器自动按 C、D、B 顺序启动三项Python服务，并设置D经HTTP访问C、B经HTTP访问D。它仅监听本机；按Ctrl+C一并停止自己启动的服务。如果端口已被使用，先检查现有程序，不要重复启动。

再开一个终端进入A目录，复制 `.env.example` 为 `.env`，把 `VITE_USE_MOCK` 改为 `false`：

```sh
cd member-a-frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。学生账号 `student / demo12345`，教师账号 `teacher / demo12345`。A单独启动时默认使用本地样例模式，页面会显示模式标签。

## 检查是否跑通

```sh
python scripts/check_integration.py
```

该脚本自行启动临时端口上的B/C/D，使用临时数据库和索引，验证登录、答案隐藏、计分、真实检索引用、合法推荐、复测、权限和教师文本导入；结束后关闭子进程，不占用日常开发端口，也不改个人数据。

各人的单元测试命令见对应README。联合验证记录见 `docs/验证记录.md`，共同字段与调用顺序见 `docs/协作接口.md`。

## 分发与继续开发

每位成员先阅读自己目录中的 `README.md` 和 `docs/开发说明.md`。独立压缩包内亦附 `docs/协作接口.md`；四人合并时保持目录名、端口及标识一致。没有安装包依赖、密钥或运行数据库随源码分发，依赖需按说明安装。

最先补齐的工作为：B的正式课程/题库/资源表及迁移，C的真实Embedding与向量检索，D的可校验模型解释，A的完整教师维护与相应异常交互。任务书的数据规模与效果目标仍需后续采集和评测。

## 官方资料

- [Vue 官方指南](https://vuejs.org/guide/)
- [Vite 启动指南](https://vite.dev/guide/)
- [FastAPI 官方教程](https://fastapi.tiangolo.com/tutorial/)
- [Chroma 使用说明](https://docs.trychroma.com/docs/overview/getting-started)
