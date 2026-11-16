# 成员 B 后端与数据项目骨架

项目：基于 RAG 与多智能体协作的个性化学习诊断与推荐系统。

当前提供账号认证、邮箱验证码、找回密码、课程与选课管理、教师题库、试卷发布、学生限时作答、自动评分、历史成绩、复测对比、诊断输入导出，以及教师资料管理、PDF/DOCX 上传、学生阅读和原件下载，数据库使用 MySQL。所有功能均不使用图片验证码。课程模块见 [课程与知识点接口说明](docs/课程与知识点接口说明.md)，测验模块见 [测验业务接口说明](docs/测验业务接口说明.md)，资料模块见 [资料业务接口说明](docs/资料业务接口说明.md)，完整入口见 [接口详细说明](docs/接口详细说明.md)。

现已提供 C 主动拉取资料、回报索引状态和 D 获取诊断输入的 6 个内部接口，使用独立服务密钥及课程白名单。启用、迁移和完整联调流程见 [内部数据接口与联调说明](docs/内部数据接口与联调说明.md)。测验结算自动创建持久化通知任务，独立 worker 向 D 交付 attempt_id，支持冻结输入和失败重试，见 [诊断任务交付说明](docs/诊断任务交付说明.md)。D 需新增任务接收端，delivered 仅表示接收成功。

## 启动

要求 Python 3.11 或以上。在本目录打开终端：

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env
python -m app
```

Windows 可手动复制 `.env.example` 为 `.env`。已有 `.env` 时直接编辑，避免覆盖配置。

也可以使用 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` 开发启动。浏览器打开 `http://127.0.0.1:8000/docs` 查看并操作接口。

当前启动过程不会自动创建账号。先获取邮箱验证码，再调用 `/user/register` 注册，可通过 `role` 选择 `student`（学生）或 `teacher`（教师），不传默认学生；注册接口负责密码哈希处理。登录后在文档的 Authorize 中填写返回的访问令牌。

## 目录

```text
app/
  __init__.py
  __main__.py         python -m app 启动入口
  main.py             FastAPI 装配、启动初始化、中间件和异常处理
  api/
    __init__.py       统一成功响应
    auth.py           用户登录、退出及当前用户信息，旧 auth 路由未挂载
    user.py           邮箱验证码发送、用户注册、重置密码
    courses.py        已发布课程目录、课程详情、学生选退课
    teacher.py        教师自己的课程、章节和知识点管理
    exams.py          教师题库、试卷及学生作答、成绩与诊断数据导出
    resources.py      教师资料管理、文件上传与学生阅读/下载
    internal.py       C 课程/资料读取、索引回报和 D 诊断输入
    diagnosis_tasks.py 学生/教师查询、补建及重试诊断通知
  services/
    __init__.py
    scoring.py        独立评分算法
    verification.py   验证码生成、摘要与存储
    registration.py   注册校验与事务
    password_reset.py 重置密码及撤销旧会话
    courses.py        课程状态、归属权限、选课人数及选退课事务
    exams.py          题库、试卷快照、作答保存、评分及超时结算事务
    assessment.py     测验评分、知识点统计和复测对比纯函数
    resources.py      资料权限、知识点关联、版本及逻辑删除事务
    resource_files.py PDF/DOCX 提取、私有原件保存和下载权限
    resource_index.py 规范化资料摘要、索引状态和事务内待同步标记
    internal.py       内部数据权限、清单、回报及完整诊断数据组装
    diagnosis_tasks.py 评分同事务入队、任务权限及状态
    diagnosis_dispatch.py 输入冻结、租约领取、D 通知和可恢复重试
    mail.py           SMTP 邮件发送
  models.py           账号、课程、题库、测验、资料等十九个启用 ORM 模型
  schemas.py          请求数据校验
  exam_schemas.py     测验请求数据校验
  resource_schemas.py 资料请求及更新版本校验
  internal_schemas.py 内部索引回报参数校验
  internal_security.py C/D 服务密钥及课程白名单
  expire_attempts.py  超时作答批量结算命令
  dispatch_diagnoses.py 独立诊断通知 worker（--watch 持续轮询）
  database.py         SQLAlchemy 引擎、会话、ORM 基类
  security.py         密码、令牌和权限检查
  dependencies.py     公共数据库、用户、教师依赖
  clients.py          C 服务 HTTP 客户端
  fixtures.py         静态演示课程、题目、知识点、资源目录
  config.py           .env 与默认配置
```

## 数据库

先创建 MySQL 数据库及专用账号，再在根目录 `.env` 设置：

```dotenv
DATABASE_URL=mysql+pymysql://course_user:change_me@127.0.0.1:3306/learning_diagnosis?charset=utf8mb4
```

`app.database` 和应用配置统一读取上述地址，不再默认使用 SQLite。启动时会创建缺失的十九张表：`users`、`login_sessions`、`email_verification_codes`、`courses`、`course_chapters`、`knowledge_points`、`course_enrollments`、`questions`、`question_options`、`question_knowledge_points`、`exams`、`exam_questions`、`exam_attempts`、`exam_answers`、`course_resources`、`resource_knowledge_points`、`resource_files`、`resource_index_states`、`diagnosis_tasks`。连接或建表失败会阻止应用启动。MySQL 数据库本身需要提前创建，连接账号需要建表权限。建议使用 MySQL 8.0.16+。也可以手动执行：

```sh
python -c 'from app.database import Base, engine; import app.models; Base.metadata.create_all(engine)'
```

这会创建当前启用模型对应的缺失表。课程、选课、测验和资料均已接入 HTTP 接口；`fixtures.py` 中的静态样例不会自动写入数据库。`create_all` 不会更新已有表；已有数据库的列、主键及约束变更需要单独迁移。资料的独立建表文件见 [create_course_resource_tables.sql](sql/create_course_resource_tables.sql)。

资料索引状态的建表及历史 pending 回填见 [create_resource_index_states.sql](sql/create_resource_index_states.sql)，已有数据库在维护窗口完整执行；重复执行保留已有状态，不能将历史资料直接标为 ready。

诊断通知独立建表见 [create_diagnosis_tasks.sql](sql/create_diagnosis_tasks.sql)，不自动为历史测验创建任务。自动入队默认开启，Web 与 D 之间由独立 `python -m app.dispatch_diagnoses --watch` 进程交付；D 接收端和双向密钥配置见任务交付文档。

`course_enrollments` 使用课程、学生联合主键。选退课服务会保留 withdrawn 记录，重新加入时恢复同一行并更新加入时间；仅学生可操作本人选课，且只能加入 published 课程。教师课程列表和详情按 active 记录统计人数，不接受手动修改人数。

先修关系模型及相关服务已删除。若现有数据库保留了历史 `knowledge_prerequisites` 表，删除代码和重启不会自动删除该表，需单独进行数据库清理。

用户、两门课程、章节、知识点和学生选课的演示初始化 SQL 见 [sql/README.md](sql/README.md)，脚本路径为 `sql/seed_teacher_student_courses.sql`。脚本保留已有账号密码，不会自动执行到数据库。

上述两门课程各 10 道题、各一份已发布试卷的初始化文件为 [seed_teacher_questions_exams.sql](sql/seed_teacher_questions_exams.sql)。每份试卷 100 分、30 分钟，包含选项、教师解析和发布快照；先准备课程基础数据，再按 SQL 说明执行。

登录会话只保存 Token 的 SHA-256 哈希，默认有效期为一天；成功登录时清理到期会话，退出时删除当前会话，删除用户时级联删除其会话。

## 注册验证码与邮件发送

`POST /user/send-register-code` 接收邮箱，通过 SMTP 发送六位数字注册验证码（包含前导零）。数据库只保存 HMAC-SHA256 摘要，HTTP 响应不返回验证码。收到邮件后调用 `/user/register` 完成注册。

使用前，在 `.env` 中填写以下配置并重启服务。独立密钥 `EMAIL_VERIFICATION_SECRET` 至少 32 字节，可运行 `python -c 'import secrets; print(secrets.token_hex(32))'` 生成后保存，不要为每次请求重新生成。

```dotenv
EMAIL_VERIFICATION_SECRET=填写生成的随机密钥
SMTP_HOST=填写邮件服务商的SMTP服务器
SMTP_PORT=465
SMTP_USERNAME=sender@example.com
SMTP_PASSWORD=填写SMTP授权码或服务商提供的密码
SMTP_FROM=sender@example.com
SMTP_SECURITY=ssl
SMTP_TIMEOUT=10
```

支持 `ssl`（常用端口 465）和 `starttls`（常用端口 587），具体按邮件服务商要求配置；两种方式都会验证服务端证书。`SMTP_FROM` 留空时使用 `SMTP_USERNAME`，发件人需符合邮件服务商的发信权限。

请求示例：

```sh
curl -X POST http://127.0.0.1:8000/user/send-register-code \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com"}'
```

成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "sent": true,
    "email": "student@example.com",
    "expires_in": 300,
    "retry_after": 60
  },
  "request_id": "请求追踪ID"
}
```

验证码有效期为 300 秒，同一邮箱每 60 秒可重新发送一次。重复请求返回 HTTP 429，`Retry-After` 响应头表示剩余等待秒数；邮箱格式不正确或含多余字段返回 422，SMTP 或密钥未配置返回 503，SMTP 发送失败返回 502，数据库故障返回 503。`sent` 表示 SMTP 服务已接受邮件，不保证邮件一定进入收件箱。

内部服务 `issue_registration_code(db, email, deliver=send_registration_code_email)` 使用独立数据库会话，负责提交或回滚事务。MySQL 行锁与唯一约束串行化同一邮箱的并发请求。发送成功后提交新摘要并重置尝试次数和使用状态；发送失败回滚，旧验证码不会因本次失败被覆盖。SMTP 发送与 MySQL 提交不属于同一个事务：若邮件已发送但数据库提交失败，接口返回错误，该邮件中的验证码不能保证有效，需要重新获取。原始验证码不写入数据库或日志。

## 用户注册

`POST /user/register` 无需登录，请求示例：

```json
{
  "username": "student01",
  "email": "student@example.com",
  "role": "student",
  "password": "Example123!",
  "confirm_password": "Example123!",
  "verification_code": "082391"
}
```

用户名去除首尾空白后长度为 3～64，仅允许中文等 Unicode 字母、数字、下划线和连字符；邮箱使用与发验证码时相同的格式校验，并转为小写。密码为 8～128 位，至少包含一个英文字母和一个数字，不能包含控制字符；密码中的空格会保留。确认密码必须完全一致。验证码必须是六位 ASCII 数字字符串，保留开头的零。`role` 可选 `student` 或 `teacher`，不传默认 `student`；传入其他角色、空字符串或 `null` 返回 422。请求不接受未定义字段。

后端锁定该邮箱对应的注册验证码记录，检查有效期、使用状态、错误次数，并使用恒定时间比较校验摘要。错误尝试会持久化；第 5 次错误及之后的尝试返回 429，需要重新获取验证码。新验证码会重置错误次数。

成功返回 HTTP 201，`data` 为：

```json
{"id": 42, "username": "student01", "email": "student@example.com", "role": "student"}
```

教师注册时将请求的 `role` 改为 `teacher`；注册、登录及用户信息响应会返回实际保存的角色。无需修改数据库表结构。

密码通过现有的加盐 PBKDF2-HMAC-SHA256 实现处理，仅将 `password_hash` 入库，不存确认密码。创建用户和标记验证码已使用在同一个 MySQL 事务中提交，提交失败则一起回滚；并发请求由验证码行锁和账号唯一约束保护。响应不包含密码、密码哈希或验证码。注册成功后仍需调用 `/user/login` 登录。

输入校验失败返回 422，验证码不正确、缺失、过期或已使用返回 400，用户名或邮箱重复返回 409，验证码错误次数达到上限返回 429，验证码密钥未配置或数据库故障返回 503。验证码密钥必须与发信时一致。新增注册接口不需要更改现有表结构。

## 登录、用户信息与退出

`POST /user/login` 提交用户名和密码，不需要任何验证码：

```json
{"username": "student01", "password": "Example123!"}
```

用户名去除首尾空白后须为 3～64 位单词字符或连字符，密码为 8～128 位。验证通过后创建 24 小时登录会话，返回 `access_token`、`token_type` 和用户基本信息。数据库只保存 Token 摘要。

`GET /user/info` 携带 `Authorization: Bearer <access_token>`，返回当前用户的 `username`、`role`、`email`。`POST /user/exit` 携带同样的请求头，删除当前会话；其他设备会话不受影响。当前未挂载旧 `/auth/login`、`/auth/logout`，请使用 `/user` 路径。

## 找回密码

先调用 `POST /user/send-reset-password-code`，提交已注册邮箱：

```json
{"email": "student@example.com"}
```

后端校验邮箱格式和账号存在性，向该邮箱发送重置验证码。有效期 5 分钟，同一邮箱、同一用途发送间隔 60 秒；未注册邮箱返回 404。重置用途 `reset_password` 与注册用途 `register` 分开存储和计数。

收到邮件后调用 `POST /user/resetPassword`：

```json
{
  "email": "student@example.com",
  "verification_code": "082391",
  "password": "NewPassword456!",
  "confirm_password": "NewPassword456!"
}
```

两次新密码必须一致，强度规则与注册相同。验证码格式、有效期、使用状态及最多 5 次错误限制均在后端检查。成功返回 `data: {"password_reset": true}`，密码哈希更新、验证码消费及该用户所有会话删除在同一事务提交。旧密码和所有旧 Token 随后失效，需使用新密码登录。接口不需要旧密码或图片验证码，也不会直接在最终重置接口中发邮件。

上述功能复用现有三张表和 SMTP 配置，无需新增表结构；重启服务即可加载新路由。完整参数、响应和错误码见接口文档。

## 联调

前端直接调用 `/user` 账号接口、`/teacher/courses` 教师课程接口、`/courses` 学生目录与选课接口，没有 `/api/v1` 前缀。教师先创建草稿、添加章节和有效知识点，再 PATCH 发布；学生浏览 published 课程后选课。完整调用流程见 [课程与知识点接口说明](docs/课程与知识点接口说明.md)。

教师建立 active 题目，创建草稿试卷、配置题目及分值后发布。学生选课后开始测验，取得题目快照，用选项 ID 和 revision 保存答案，保存成功后提交。发布快照不随题库修改而变化；每名学生每份试卷仅一次，复测使用另一份试卷关联基准记录。完整请求示例见 [测验业务接口说明](docs/测验业务接口说明.md)。

超时会在访问作答/结果时结算；需要及时批量结算时，由调度器周期运行 `python -m app.expire_attempts --limit 100`。服务端截止时间始终有效，即使未启用调度器也不能在超时后修改答案。

C 使用 C_SERVICE_KEY 主动拉取资料并回报索引状态。D 使用 D_SERVICE_KEY 读取数据；已有按作答实时导出，正式任务则读取通知中的 `/internal/diagnosis-tasks/{task_id}/input` 冻结快照。B 已在测验结算时自动持久化任务，由独立 worker 用 DIAGNOSIS_SERVICE_KEY 通知 D。D 当前旧接口尚不能接收任务 ID，需按 [诊断任务交付说明](docs/诊断任务交付说明.md) 增加接收端；尚无诊断完成回调或报告落库。教师旧导出接口继续兼容旧 D 模型。B 不主动调用 C。

教师通过 POST `/teacher/courses/{course_id}/resources` 创建资料，PATCH `/teacher/resources/{resource_id}` 携带 expected_version 修改，DELETE 逻辑删除；学生通过课程 resources 列表及 `/resources/{resource_id}` 阅读。资料关联同课程知识点，正文支持最多 20 万字符。创建及实际更新/删除在同一事务标记索引 pending；资料响应新增 index_status。只有 C 确认当前版本 ready，资料才进入新的内部诊断目录。完整示例见 [资料业务接口说明](docs/资料业务接口说明.md)。

文件上传使用 POST `/teacher/courses/{course_id}/resources/upload`，在 Swagger 中选择 PDF/DOCX，knowledge_point_ids 每项填单个 ID；接口兼容重复同名字段、英文逗号分隔及旧 JSON 数组字符串。上传后保留原件，可通过教师/学生各自的 resources/{resource_id}/file 路径鉴权下载。先执行 `python -m pip install -r requirements.txt` 并重启；文件最多 10 MiB，扫描 PDF 暂不做 OCR，旧 .doc 需另存 .docx。原件默认保存到私有 `data/resource_files`，可配置 RESOURCE_UPLOAD_DIR。完整操作见 [资料文件上传说明](docs/资料文件上传说明.md)。

上层项目的 `../scripts/start_services.py`、`../scripts/check_integration.py` 仍引用旧入口 `backend_service.main:app`，需要同步改为 `app.main:app`；联调检查中的旧测验流程也需要调整。这些文件位于当前可写工作区之外，本次未修改。当前请使用上面的命令直接启动 B。

## 测试

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_auth_sessions.py tests/test_startup.py tests/test_verification.py tests/test_registration_mail.py tests/test_registration.py tests/test_user_account.py tests/test_courses.py tests/test_exams.py tests/test_resources.py tests/test_resource_files.py tests/test_internal.py tests/test_diagnosis_tasks.py tests/test_mysql_exams.py tests/test_mysql_seed_exams.py tests/test_mysql_resources.py tests/test_mysql_internal.py tests/test_mysql_diagnosis_tasks.py
```

默认回归使用模拟数据库会话、MySQL SQL 方言及模拟 SMTP，覆盖账号、课程、选课、测验和资料的规则、权限、版本及故障回滚，不访问业务数据库或真实邮箱。test_mysql_*.py 中的真实数据库测试只有显式设置 TEST_MYSQL_URL 才会运行：创建独立随机测试库、完成真实链路后删除该临时库，不使用 DATABASE_URL 的业务库；配置方法见对应模块文档。原有 `tests/test_backend.py` 依赖旧版 SQLite 初始化流程，尚未迁移，不包含在上述回归命令中。

当前文档见 [数据模型详细说明](docs/数据模型详细说明.md)、[接口详细说明](docs/接口详细说明.md)、[开发说明](docs/开发说明.md) 和 [协作接口](docs/协作接口.md)。
