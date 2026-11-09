# 成员 B 后端与数据项目骨架

项目：基于 RAG 与多智能体协作的个性化学习诊断与推荐系统。

本目录负责登录权限、课程与知识点目录、题库及资料管理、客观题评分、作答存储、错题与进度数据、诊断服务接入和教师接口。默认使用 SQLite；首次启动自动加入一门数据结构课程、两个知识点与六道自编题作为演示数据。教师可以创建课程、知识点和单选题，编辑或停用题目，并导入课程资料。

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

远程 `gh` 分支的完整前端 `full-v1` 契约已由 B 实现在 `/api/v2`；现有 `/api/v1` 仍用于 `group-v0`。完整前端运行 `dev:real` 时须在其 `.env.real.local` 设置 `VITE_API_BASE_URL=/api/v2`。37 个接口的范围、调用示例与验证记录见项目根目录的 [gh 前端接口对接说明](../成员B_gh前端接口对接说明.md)。

## 独立开发与四人联调

- 单独运行 B 时，取题、评分、历史记录仍可工作。未启动 D 时，成绩保留，`report` 为 `null`，`ai_status` 为 `unavailable`。
- 只调业务可在 `.env` 设置 `AGENTS_MODE=disabled`。
- 需要完整本地流程时，先启动 C 的 8001 服务及 D 的 8002 服务；D 设 `RAG_MODE=http`，B 保持 `AGENTS_MODE=http`，A 设 `VITE_USE_MOCK=false`。
- 教师可通过 JSON 正文或 Base64 文件导入文本、Markdown、可提取文字的 PDF；B 将正文交给 C 建索引。A 的上传与完整管理表单仍待接入。

## 测试

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试使用隔离临时数据库，不改演示数据库。覆盖登录与退出、角色和记录权限、答案隐藏、计分、幂等提交、教师题库、历史快照、错题、练习、进度、资料导入与删除以及引用式问答。

## 中期新增接口

| 方法及路径 | 用途 |
| --- | --- |
| GET `/api/v1/courses/{course_id}/knowledge-points` | 学生查看知识点及题数 |
| POST `/api/v1/teacher/courses` | 教师创建课程 |
| POST `/api/v1/teacher/courses/{course_id}/knowledge-points` | 教师创建知识点 |
| POST `/api/v1/teacher/courses/{course_id}/questions` | 教师创建单选题 |
| GET `/api/v1/teacher/courses/{course_id}/questions` | 教师查看题库及标准答案 |

学生的 GET `/api/v1/courses/{course_id}/questions` 始终隐藏标准答案。详细字段和请求示例见 [开发说明](docs/开发说明.md)。

## 功能扩展

新增错题本、按知识点练习、进度数据、题库编辑停用、教师资料列表/状态/删除、`.txt`/`.md`/`.pdf` 文件导入和带来源引用的课程问答。旧 `/api/v1` 的文件导入采用 JSON 中的 Base64 字段；新 `/api/v2/teacher/documents` 使用 multipart 上传并返回处理任务。PDF 使用 `pypdf` 提取文字，扫描件需先 OCR。课程问答只摘录 C 返回的证据，不调用大语言模型。旧接口详情见项目根目录的 [成员 B 功能扩展记录](../成员B_功能扩展实现记录.md)。

## 下一步

下一阶段补版本化数据库迁移、MySQL 验证与文件 OCR。A 侧可按 `/api/v2` 接入完整页面并完成浏览器逐页验收。成员 B 的中期计划与实际完成情况见项目根目录的 `成员B_中期项目计划与实现记录.md`。
