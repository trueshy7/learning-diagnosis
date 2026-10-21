# 成员 B 后端与数据项目骨架

项目：基于 RAG 与多智能体协作的个性化学习诊断与推荐系统。

本目录负责登录权限、课程取题、客观题评分、作答存储、诊断服务接入和教师接口。默认使用 SQLite 及六道自编客观题，不需要先安装 MySQL。它是可运行的起步工程，尚未完成任务书中的全部业务功能与数据规模。

## 启动

要求 Python 3.11 或以上。在本目录打开终端：

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env
python -m backend_service
```

Windows 可手动复制 `.env.example` 为 `.env`。配置文件会自动加载；服务只监听本机 `127.0.0.1:8000`。浏览器打开 `http://127.0.0.1:8000/docs` 查看并操作接口。

演示账号：学生 `student / demo12345`，教师 `teacher / demo12345`。首次启动自动创建账号，密码经哈希保存。登录后在文档的 Authorize 中填写返回的访问令牌。

## 独立开发与四人联调

- 单独运行 B 时，取题、评分、历史记录仍可工作。未启动 D 时，成绩保留，`report` 为 `null`，`ai_status` 为 `unavailable`。
- 只调业务可在 `.env` 设置 `AGENTS_MODE=disabled`。
- 需要完整本地流程时，先启动 C 的 8001 服务及 D 的 8002 服务；D 设 `RAG_MODE=http`，B 保持 `AGENTS_MODE=http`，A 设 `VITE_USE_MOCK=false`。
- 教师资料接口目前接收 JSON 文本并交给 C；二进制文件上传、PDF 解析和完整管理表单后续补充。

## 测试

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试使用隔离临时数据库，不改演示数据库。覆盖登录与退出、角色和记录权限、答案隐藏、计分、非法选项、重复题目、幂等提交和 AI 未启用时的成绩保存。

## 下一步

先阅读 [开发说明](docs/开发说明.md)，再将静态题库迁移到正式关系表，补齐课程管理、文件上传和接口测试。数据库迁移、MySQL 验证和异步诊断任务均有明确扩展位置。
