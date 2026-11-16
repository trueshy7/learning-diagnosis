# 数据库 SQL 使用说明

资料业务建表文件：[create_course_resource_tables.sql](create_course_resource_tables.sql)。它创建 course_resources、resource_knowledge_points、resource_files 三张缺失表，不插入演示资料；重启新版后端也会自动建缺失表。已存在同名表时不修改列或约束，实际结构需核验 SHOW CREATE TABLE。使用前修改目标库名，确保父表和同课程复合唯一键已存在。资料字段和接口见 [资料业务接口说明](../docs/资料业务接口说明.md)。已有正文表、只需增加文件功能时可执行 [create_resource_file_table.sql](create_resource_file_table.sql)；文件依赖、私有目录与表单说明见 [资料文件上传说明](../docs/资料文件上传说明.md)。

## 演示数据初始化

课程基础数据：[seed_teacher_student_courses.sql](seed_teacher_student_courses.sql)。

题库与测验数据：[seed_teacher_questions_exams.sql](seed_teacher_questions_exams.sql)，需在课程基础数据之后执行，说明见本文末尾。

## 数据内容

| 对象 | 内容 |
| --- | --- |
| 学生 | `id=1`，用户名 `admin`，角色 `student` |
| 教师 | `id=2`，用户名 `teacherAdmin`，角色 `teacher` |
| 课程 | 教师 id=2 的“数据结构基础”“Python 程序设计基础”，均为 published |
| 章节 | 每门课程两个，共四个 |
| 知识点 | 每章节两个，共八个，均为 active |
| 选课 | 学生 id=1 选上上述两门课，两条 active 记录 |

脚本中的用户邮箱和密码哈希使用用户提供的数据，不包含或生成明文密码。它不会创建登录会话、邮箱验证码或先修关系。

## 执行

1. 先启动后端，使当前模型对应的表和约束已经创建。
2. 默认目标数据库为 `learning_diagnosis`，如实际数据库名不同，修改 SQL 文件开头的 `USE`。
3. 在支持 MySQL `DELIMITER` 的客户端中运行完整脚本。例如在项目根目录执行：

```sh
mysql --default-character-set=utf8mb4 -h 127.0.0.1 -P 3306 -u root -p < sql/seed_teacher_student_courses.sql
```

密码由客户端交互输入。脚本使用存储过程包装事务，账号需具备数据读写、`CREATE ROUTINE`、`ALTER ROUTINE`、`EXECUTE` 权限。执行出错会回滚数据事务并抛出错误，不要以忽略错误的模式继续运行。临时存储过程正常结束后删除；如果中途失败，重复执行文件会先清理同名过程。

## 重复执行规则

- 已有用户不更新密码、用户名、邮箱或角色；账号 ID、名称、邮箱、角色须与预期一致，否则停止并回滚，避免错误关联他人账号。
- 课程和章节使用固定的 `demo-` 前缀 ID，不与原静态样例 `course-ds` 混用。重跑会更新这些演示记录的名称、介绍和排序，课程恢复 published，知识点恢复 active。
- 演示课程 ID 如果属于其他教师，脚本停止并回滚。
- 已存在的 active 选课不会重复创建，也不会重置加入时间；withdrawn 记录恢复 active 并更新时间。
- 课程、章节的原创建时间保留。脚本不会删除其他课程、用户或学习数据，不会关闭外键检查。

最后三个 SELECT 用于核验用户、课程及学生选课；其中每门演示课程应有 2 个章节、4 个知识点，学生 admin 应有两条有效选课。其他学生也选了这两门课程时，课程总选课人数可以大于 1。

该脚本由代码模型及约束核对生成，未自动执行到真实数据库。

## 题库与测验初始化

新增文件：[seed_teacher_questions_exams.sql](seed_teacher_questions_exams.sql)。沿用上面的教师和两门课程，不额外创建课程或账号。

| 课程 | 课程 ID | 试卷 ID | 题目 |
| --- | --- | --- | --- |
| 数据结构基础 | `demo-course-ds-teacher-2` | `demo-exam-ds-teacher-2` | 栈概念、栈操作、队列概念、队列操作，共 10 道 |
| Python 程序设计基础 | `demo-course-python-teacher-2` | `demo-exam-python-teacher-2` | 变量赋值、基础类型、条件判断、循环，共 10 道 |

每门课 8 道单选、2 道多选，每题 4 个选项；题目 active，试卷 published。每份试卷 10 题，每题 10 分，共 100 分，限时 1800 秒。题目 ID 分别为 `demo-q-ds-01`～`demo-q-ds-10`、`demo-q-python-01`～`demo-q-python-10`。

同时写入 `questions`、`question_options`、`question_knowledge_points`、`exams`、`exam_questions` 五张表；包含教师解析、正确答案，以及与发布接口一致的题目 JSON 快照和课程 active 知识点目录快照，可直接用于学生作答和评分。不创建作答、答案或成绩，不改变账号和选课数据。

### 执行顺序

1. 重启当前后端，确保测验表已创建。
2. 尚未导入课程基础数据时，先执行 `seed_teacher_student_courses.sql`；已存在对应数据则无需重跑基础脚本。
3. 确认 teacherAdmin 的 ID 为 2、角色 teacher，上述课程属于他且为 published，八个演示知识点存在且 active。
4. 根据实际库名修改新 SQL 文件开头的 `USE learning_diagnosis`，在支持 DELIMITER 的 MySQL 客户端完整执行：

```sh
mysql --default-character-set=utf8mb4 -h 127.0.0.1 -P 3306 -u root -p < sql/seed_teacher_questions_exams.sql
```

使用 MySQL 8.0.16+。脚本使用存储过程本地 JSON 变量、JSON_TABLE、JSON_OBJECT、JSON_ARRAYAGG，不再使用临时表，无需 CREATE TEMPORARY TABLES 权限。账号需要前述存储过程和业务表权限。可在 PyCharm 数据库控制台中按完整脚本运行，需启用客户端对 DELIMITER 的支持；不要逐条拆开过程体执行。

### 重跑与验证

- 两门课的数据写入在一个事务中，任一课程失败会回滚本次业务写入；不关闭外键检查，不使用 REPLACE 或 INSERT IGNORE。
- 已有完整的 published/archived 演示试卷（10 个指定题目快照、总分 100）时，保留其题库、快照、时长、归档状态和已有作答，不覆盖内容，也不重复插入。
- 如果同名演示题目/选项存在但没有对应试卷，或已有试卷是草稿、课程不匹配、题目不完整，脚本会停止，便于先核对冲突数据。
- JSON 变量随过程调用结束释放；成功后删除辅助过程。失败会回滚业务写入，再次执行文件会先清理同名存储过程。
- 最后第一个 SELECT 返回两份试卷，question_count、actual_question_count、snapshot_count 应均为 10，总分 100；第二个 SELECT 展示 20 道题的知识点及分值。

执行后教师可 GET `/teacher/courses/{course_id}/questions` 和 `/teacher/courses/{course_id}/exams` 核验；已经选课的学生可 GET `/courses/{course_id}/exams`，再 POST `/exams/{exam_id}/attempts` 开始作答。完整流程见 [测验业务接口说明](../docs/测验业务接口说明.md)。

每门课四个知识点的题量为 3、3、2、2；按当前“至少三题才判断掌握状态”的规则，后两个知识点返回 insufficient_evidence，这是 10 题配置下的预期行为。

题目参数、选项和正确答案已按当前请求模型及评分规则校验；尚未自动在真实 MySQL 中执行本脚本。

### 1137 错误后的重试

旧版过程使用临时表，在执行时可能报 `1137 - Can't reopen table: 'sq'`。新版已将种子数据改为过程本地 JSON 变量，避免临时表的重复打开限制。MySQL 的限制说明见 [官方文档](https://dev.mysql.com/doc/refman/8.0/en/temporary-table-problems.html)。

更新文件后应从 `DROP PROCEDURE IF EXISTS`、`CREATE PROCEDURE` 到 `CALL` **重新完整执行新版脚本**；仅重复运行 CALL 仍会调用数据库里保存的旧过程。原过程的异常处理会执行 ROLLBACK；新版仍保留同一事务、冲突检查、重跑保护和发布快照。

新增 `tests/test_mysql_seed_exams.py`：默认校验 SQL 内的实际题目 JSON；显式配置 TEST_MYSQL_URL 后，另在随机独立测试库完整执行前置课程 SQL 和测验 SQL，检查 1137 回归、80 个选项、真实作答评分、重跑保留历史，以及第二门课失败时两门课一并回滚。测试不会使用业务库：

```sh
python -m pytest -q tests/test_mysql_seed_exams.py
```

真实集成测试需测试账号具备建库、删库及过程执行权限；未配置连接时跳过，不能把静态检查视为真实 MySQL 执行验证。

## 诊断通知任务表

诊断通知独立建表文件为 [create_diagnosis_tasks.sql](create_diagnosis_tasks.sql)。修改 USE 后执行，或启动时创建缺失表；不修改旧表，不自动为历史作答入队。新结算会在成绩事务中自动创建通知，历史已完成测验可用本人学生/所属教师的 POST diagnosis-task 补建。D 接收契约、双向密钥、独立 worker、冻结输入和重试见 [诊断任务交付说明](../docs/诊断任务交付说明.md)。

## 资料索引状态迁移

资料索引状态的独立迁移为 [create_resource_index_states.sql](create_resource_index_states.sql)。在维护窗口停止业务写入，修改 USE 后完整执行，创建 resource_index_states 并只为缺少状态的历史资料（含已删除记录）回填 pending；重复执行不会覆盖 ready/failed/deleted 等已有结果，不修改资料正文、版本或原文件。DDL 会隐式提交，无法把整份脚本作为单个事务回滚。父表及外键列排序规则需一致；启动 create_all 只建缺失表，不会替代历史回填。启用 C/D 凭证和联调步骤见 [内部数据接口与联调说明](../docs/内部数据接口与联调说明.md)。

## 开始测验 503：检查旧表是否缺少快照列

当前 ExamAttempt 模型需要 `exam_attempts.knowledge_snapshot`。如果表在添加此字段之前已创建，启动时的 create_all 不会补列；开始测验查询作答记录就可能抛出 MySQL 1054，并被服务转换为统一的 503。该响应本身不足以断定所有 503 都由缺列造成。

先在实际目标库执行：

```sql
SHOW COLUMNS FROM exam_attempts LIKE 'knowledge_snapshot';
```

若无结果，使用 [repair_exam_attempt_knowledge_snapshot.sql](repair_exam_attempt_knowledge_snapshot.sql)。按实际库名修改文件开头 USE，然后完整执行文件（需要 ALTER、存储过程及数据读写权限）。文件检查字段是否存在，缺失时补 JSON 列；已有作答从所属试卷复制发布时的知识点目录，再设为 NOT NULL。已有非 NULL 快照和其他作答、答案、成绩保持不变，可重复执行。ALTER TABLE 会隐式提交，无法将整份 DDL 修复作为单个事务回滚。

执行后应能查询到 `knowledge_snapshot / json / NO`，再重试 POST `/exams/{exam_id}/attempts`。如果字段已经存在仍报 503，需要查看后端终端中的原始数据库异常，继续核对其他列、连接或权限问题，不要删除业务表或重导数据来猜测修复。

`tests/test_mysql_seed_exams.py` 包含缺列回归：独立测试库中移除该列，验证开始测验返回 503/原始 1054；执行修复 SQL 后确认历史记录保留、新测验可开始，重复执行不影响数据。未配置 TEST_MYSQL_URL 时跳过真实执行。
