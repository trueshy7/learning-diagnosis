-- MySQL 8.0.16+：为 teacherAdmin(id=2) 的两门演示课程生成题库及已发布试卷。
-- 前置：启动后端建表，并先执行 seed_teacher_student_courses.sql。
-- 两门课各 10 道题（8 单选 + 2 多选）、一份 10 题试卷；每题 10 分，总分 100，限时 1800 秒。
-- 包含正确选项、教师解析、知识点关联及发布快照；不会创建学生作答或更改账号/选课。
-- 重跑保留已有完整的 published/archived 演示试卷及题库，不覆盖历史快照。
-- 冲突、缺少前置数据或不完整的已有演示试卷都会报错并回滚本次两门课程的数据写入。
-- 执行账号需有 CREATE ROUTINE / ALTER ROUTINE / EXECUTE 和业务表读写权限。
-- 如数据库名称不同，请修改下面的 USE；请在独立会话中整体执行，不使用忽略错误模式。

USE `learning_diagnosis`;
SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS `seed_demo_teacher_questions_exams`;
DELIMITER $$
CREATE PROCEDURE `seed_demo_teacher_questions_exams`()
BEGIN
    DECLARE seed_now BIGINT;
    DECLARE seed_index INT DEFAULT 0;
    DECLARE seed_course VARCHAR(64);
    DECLARE seed_exam VARCHAR(64);
    DECLARE seed_title VARCHAR(100);
    DECLARE seed_teacher INT;
    DECLARE seed_course_status VARCHAR(20);
    DECLARE seed_existing_course VARCHAR(64);
    DECLARE seed_existing_status VARCHAR(20);
    DECLARE seed_existing_count INT;
    DECLARE seed_existing_total DECIMAL(8, 2);
    DECLARE seed_questions JSON;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET seed_now = UNIX_TIMESTAMP();
    -- 使用本地 JSON 变量，避免 MySQL TEMPORARY TABLE 的 1137 重开限制。
    SET seed_questions = JSON_ARRAY(
        CAST('{"id":"demo-q-ds-01","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-concept","kind":"single","stem":"栈遵循哪一种访问原则？","explanation":"栈只允许在栈顶插入和删除，最后入栈的元素最先出栈。","options":[{"id":"demo-q-ds-01-A","label":"A","text":"先进先出","is_correct":false},{"id":"demo-q-ds-01-B","label":"B","text":"后进先出","is_correct":true},{"id":"demo-q-ds-01-C","label":"C","text":"随机访问","is_correct":false},{"id":"demo-q-ds-01-D","label":"D","text":"按元素大小访问","is_correct":false}],"sort_order":0}' AS JSON),
        CAST('{"id":"demo-q-ds-02","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-concept","kind":"single","stem":"元素 A、B、C 依次全部入栈后，再连续出栈，出栈顺序是什么？","explanation":"最后入栈的 C 位于栈顶，因此依次弹出 C、B、A。","options":[{"id":"demo-q-ds-02-A","label":"A","text":"A、B、C","is_correct":false},{"id":"demo-q-ds-02-B","label":"B","text":"C、B、A","is_correct":true},{"id":"demo-q-ds-02-C","label":"C","text":"B、A、C","is_correct":false},{"id":"demo-q-ds-02-D","label":"D","text":"A、C、B","is_correct":false}],"sort_order":1}' AS JSON),
        CAST('{"id":"demo-q-ds-03","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-concept","kind":"multiple","stem":"关于栈的描述，哪些是正确的？","explanation":"栈的逻辑特征与元素类型无关；函数调用返回需要遵循后调用先返回的顺序。","options":[{"id":"demo-q-ds-03-A","label":"A","text":"栈具有后进先出的特征","is_correct":true},{"id":"demo-q-ds-03-B","label":"B","text":"入栈和出栈都在栈顶进行","is_correct":true},{"id":"demo-q-ds-03-C","label":"C","text":"函数调用的嵌套返回可以用栈理解","is_correct":true},{"id":"demo-q-ds-03-D","label":"D","text":"栈只能存放整数","is_correct":false}],"sort_order":2}' AS JSON),
        CAST('{"id":"demo-q-ds-04","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-operations","kind":"single","stem":"空栈依次执行 push(1)、push(2)、pop()、push(3)，此时栈顶元素是什么？","explanation":"pop 移除 2，随后将 3 入栈，此时栈顶为 3。","options":[{"id":"demo-q-ds-04-A","label":"A","text":"1","is_correct":false},{"id":"demo-q-ds-04-B","label":"B","text":"2","is_correct":false},{"id":"demo-q-ds-04-C","label":"C","text":"3","is_correct":true},{"id":"demo-q-ds-04-D","label":"D","text":"栈为空","is_correct":false}],"sort_order":3}' AS JSON),
        CAST('{"id":"demo-q-ds-05","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-operations","kind":"single","stem":"对非空栈执行 peek（读取栈顶）后，栈中元素个数如何变化？","explanation":"peek 只读取栈顶元素，不执行出栈，也不改变元素个数。","options":[{"id":"demo-q-ds-05-A","label":"A","text":"增加一个","is_correct":false},{"id":"demo-q-ds-05-B","label":"B","text":"保持不变","is_correct":true},{"id":"demo-q-ds-05-C","label":"C","text":"减少一个","is_correct":false},{"id":"demo-q-ds-05-D","label":"D","text":"全部清空","is_correct":false}],"sort_order":4}' AS JSON),
        CAST('{"id":"demo-q-ds-06","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-stack-operations","kind":"multiple","stem":"哪些操作属于常见的栈操作？","explanation":"push、pop、peek 是栈的常见操作；enqueue 是队列的入队操作。","options":[{"id":"demo-q-ds-06-A","label":"A","text":"push：将元素压入栈顶","is_correct":true},{"id":"demo-q-ds-06-B","label":"B","text":"pop：移除栈顶元素","is_correct":true},{"id":"demo-q-ds-06-C","label":"C","text":"peek：读取栈顶但不移除","is_correct":true},{"id":"demo-q-ds-06-D","label":"D","text":"enqueue：从队尾插入元素","is_correct":false}],"sort_order":5}' AS JSON),
        CAST('{"id":"demo-q-ds-07","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-queue-concept","kind":"single","stem":"普通队列遵循哪一种访问原则？","explanation":"普通队列从队尾加入元素，从队头移除元素，因此先进入的元素先离开。","options":[{"id":"demo-q-ds-07-A","label":"A","text":"先进先出","is_correct":true},{"id":"demo-q-ds-07-B","label":"B","text":"后进先出","is_correct":false},{"id":"demo-q-ds-07-C","label":"C","text":"总是最小元素先出","is_correct":false},{"id":"demo-q-ds-07-D","label":"D","text":"随机元素先出","is_correct":false}],"sort_order":6}' AS JSON),
        CAST('{"id":"demo-q-ds-08","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-queue-concept","kind":"single","stem":"普通队列的入队和出队分别发生在哪里？","explanation":"队列在队尾添加，在队头删除，从而保持先进先出顺序。","options":[{"id":"demo-q-ds-08-A","label":"A","text":"队头入队，队尾出队","is_correct":false},{"id":"demo-q-ds-08-B","label":"B","text":"都在队头","is_correct":false},{"id":"demo-q-ds-08-C","label":"C","text":"都在队尾","is_correct":false},{"id":"demo-q-ds-08-D","label":"D","text":"队尾入队，队头出队","is_correct":true}],"sort_order":7}' AS JSON),
        CAST('{"id":"demo-q-ds-09","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-queue-operations","kind":"single","stem":"空队列依次入队 10、20，出队一次，再入队 30，此时队头元素是什么？","explanation":"第一次出队移除 10，队列剩余 20，之后 30 加到队尾，队头仍为 20。","options":[{"id":"demo-q-ds-09-A","label":"A","text":"10","is_correct":false},{"id":"demo-q-ds-09-B","label":"B","text":"20","is_correct":true},{"id":"demo-q-ds-09-C","label":"C","text":"30","is_correct":false},{"id":"demo-q-ds-09-D","label":"D","text":"队列为空","is_correct":false}],"sort_order":8}' AS JSON),
        CAST('{"id":"demo-q-ds-10","course_id":"demo-course-ds-teacher-2","exam_id":"demo-exam-ds-teacher-2","knowledge_point_id":"demo-kp-queue-operations","kind":"single","stem":"对空队列执行出队，合理的处理方式是什么？","explanation":"空队列没有可删除的元素，操作前应判空，并按约定返回无元素结果或抛出异常。","options":[{"id":"demo-q-ds-10-A","label":"A","text":"返回未初始化的任意元素","is_correct":false},{"id":"demo-q-ds-10-B","label":"B","text":"自动复制最后一个已删除元素","is_correct":false},{"id":"demo-q-ds-10-C","label":"C","text":"检查空队列并按接口约定报告下溢或无元素","is_correct":true},{"id":"demo-q-ds-10-D","label":"D","text":"自动变成栈并弹出元素","is_correct":false}],"sort_order":9}' AS JSON),
        CAST('{"id":"demo-q-python-01","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-variables","kind":"single","stem":"依次执行 x = 3、y = x、x = 5 后，y 的值是多少？","explanation":"y = x 时 y 引用整数 3；随后重新绑定 x 不会改变 y 的值。","options":[{"id":"demo-q-python-01-A","label":"A","text":"3","is_correct":true},{"id":"demo-q-python-01-B","label":"B","text":"5","is_correct":false},{"id":"demo-q-python-01-C","label":"C","text":"8","is_correct":false},{"id":"demo-q-python-01-D","label":"D","text":"执行报错","is_correct":false}],"sort_order":0}' AS JSON),
        CAST('{"id":"demo-q-python-02","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-variables","kind":"single","stem":"下列哪一个是合法的 Python 变量名？","explanation":"变量名不能以数字开头，不能使用关键字，也不能包含减号；student_score 是合法名称。","options":[{"id":"demo-q-python-02-A","label":"A","text":"2name","is_correct":false},{"id":"demo-q-python-02-B","label":"B","text":"class","is_correct":false},{"id":"demo-q-python-02-C","label":"C","text":"student_score","is_correct":true},{"id":"demo-q-python-02-D","label":"D","text":"student-score","is_correct":false}],"sort_order":1}' AS JSON),
        CAST('{"id":"demo-q-python-03","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-variables","kind":"multiple","stem":"关于 Python 变量和赋值，哪些说法正确？","explanation":"Python 赋值建立名称和对象的绑定关系，支持链式赋值，变量名区分大小写，不要求预先声明类型。","options":[{"id":"demo-q-python-03-A","label":"A","text":"赋值会将变量名绑定到对象","is_correct":true},{"id":"demo-q-python-03-B","label":"B","text":"可以使用 a = b = 1 同时赋值","is_correct":true},{"id":"demo-q-python-03-C","label":"C","text":"所有变量在首次赋值前都必须声明类型","is_correct":false},{"id":"demo-q-python-03-D","label":"D","text":"变量名区分大小写","is_correct":true}],"sort_order":2}' AS JSON),
        CAST('{"id":"demo-q-python-04","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-types","kind":"single","stem":"Python 中表达式 type(True) 对应的类型是什么？","explanation":"True 是布尔值，其直接类型为 bool；虽然 bool 是 int 的子类，但 type(True) 返回 bool。","options":[{"id":"demo-q-python-04-A","label":"A","text":"str","is_correct":false},{"id":"demo-q-python-04-B","label":"B","text":"int","is_correct":false},{"id":"demo-q-python-04-C","label":"C","text":"float","is_correct":false},{"id":"demo-q-python-04-D","label":"D","text":"bool","is_correct":true}],"sort_order":3}' AS JSON),
        CAST('{"id":"demo-q-python-05","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-types","kind":"single","stem":"Python 表达式 7 // 2 的结果是什么？","explanation":"对两个正整数使用 // 进行向下取整除法，7 // 2 的结果是整数 3。","options":[{"id":"demo-q-python-05-A","label":"A","text":"3.5","is_correct":false},{"id":"demo-q-python-05-B","label":"B","text":"3","is_correct":true},{"id":"demo-q-python-05-C","label":"C","text":"4","is_correct":false},{"id":"demo-q-python-05-D","label":"D","text":"1","is_correct":false}],"sort_order":4}' AS JSON),
        CAST('{"id":"demo-q-python-06","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-types","kind":"multiple","stem":"关于 Python 基础数据类型，哪些说法正确？","explanation":"列表可变，元组不可变；字符串不可通过索引原地修改；对字典已有键再次赋值会更新对应值。","options":[{"id":"demo-q-python-06-A","label":"A","text":"list 是可变类型","is_correct":true},{"id":"demo-q-python-06-B","label":"B","text":"tuple 是不可变类型","is_correct":true},{"id":"demo-q-python-06-C","label":"C","text":"str 中的单个字符可以通过索引原地修改","is_correct":false},{"id":"demo-q-python-06-D","label":"D","text":"dict 中的键不能重复保存为两个独立条目","is_correct":true}],"sort_order":5}' AS JSON),
        CAST('{"id":"demo-q-python-07","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-conditions","kind":"single","stem":"x = 5；若依次判断 x >= 10、elif x >= 5、else，三个分支分别输出 high、middle、low，最终输出什么？","explanation":"第一个条件为假，第二个条件为真，因此只执行 elif 分支并输出 middle。","options":[{"id":"demo-q-python-07-A","label":"A","text":"high","is_correct":false},{"id":"demo-q-python-07-B","label":"B","text":"low","is_correct":false},{"id":"demo-q-python-07-C","label":"C","text":"middle","is_correct":true},{"id":"demo-q-python-07-D","label":"D","text":"三个都会输出","is_correct":false}],"sort_order":6}' AS JSON),
        CAST('{"id":"demo-q-python-08","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-conditions","kind":"single","stem":"表达式 (1 < 2) and (3 > 4) 的结果是什么？","explanation":"and 两边都为真时结果才为真；3 > 4 为假，因此结果为 False。","options":[{"id":"demo-q-python-08-A","label":"A","text":"True","is_correct":false},{"id":"demo-q-python-08-B","label":"B","text":"False","is_correct":true},{"id":"demo-q-python-08-C","label":"C","text":"None","is_correct":false},{"id":"demo-q-python-08-D","label":"D","text":"表达式语法错误","is_correct":false}],"sort_order":7}' AS JSON),
        CAST('{"id":"demo-q-python-09","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-loops","kind":"single","stem":"执行 total = 0，然后 for i in range(1, 4): total += i，循环结束时 total 是多少？","explanation":"range(1, 4) 依次产生 1、2、3，不包含 4，总和为 6。","options":[{"id":"demo-q-python-09-A","label":"A","text":"3","is_correct":false},{"id":"demo-q-python-09-B","label":"B","text":"4","is_correct":false},{"id":"demo-q-python-09-C","label":"C","text":"6","is_correct":true},{"id":"demo-q-python-09-D","label":"D","text":"10","is_correct":false}],"sort_order":8}' AS JSON),
        CAST('{"id":"demo-q-python-10","course_id":"demo-course-python-teacher-2","exam_id":"demo-exam-python-teacher-2","knowledge_point_id":"demo-kp-python-loops","kind":"single","stem":"Python 循环中的 continue 语句有什么作用？","explanation":"continue 跳过当前轮次中尚未执行的循环体，进入下一轮迭代；退出当前循环应使用 break。","options":[{"id":"demo-q-python-10-A","label":"A","text":"跳过本轮剩余语句并继续下一轮","is_correct":true},{"id":"demo-q-python-10-B","label":"B","text":"立即退出所有嵌套循环","is_correct":false},{"id":"demo-q-python-10-C","label":"C","text":"退出当前函数","is_correct":false},{"id":"demo-q-python-10-D","label":"D","text":"重新执行程序入口","is_correct":false}],"sort_order":9}' AS JSON)
    );

    START TRANSACTION;
    IF NOT EXISTS (
        SELECT 1 FROM `users` WHERE `id` = 2 AND `username` = 'teacherAdmin' AND `role` = 'teacher'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Expected teacherAdmin (id=2, role=teacher); run course seed first';
    END IF;

    WHILE seed_index < 2 DO
        IF seed_index = 0 THEN
            SET seed_course = 'demo-course-ds-teacher-2';
            SET seed_exam = 'demo-exam-ds-teacher-2';
            SET seed_title = '数据结构基础测验';
        ELSE
            SET seed_course = 'demo-course-python-teacher-2';
            SET seed_exam = 'demo-exam-python-teacher-2';
            SET seed_title = 'Python 程序设计基础测验';
        END IF;

        -- 与应用的课程写操作使用同一课程行锁，避免导入时同时修改或开始作答。
        SET seed_teacher = NULL;
        BEGIN
            DECLARE CONTINUE HANDLER FOR NOT FOUND SET seed_teacher = NULL;
            SELECT `teacher_id`, `status` INTO seed_teacher, seed_course_status
            FROM `courses` WHERE `id` = seed_course FOR UPDATE;
        END;
        IF seed_teacher IS NULL OR seed_teacher <> 2 OR seed_course_status <> 'published' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Both demo courses must exist, belong to teacher 2 and be published';
        END IF;

        SET seed_existing_course = NULL;
        BEGIN
            DECLARE CONTINUE HANDLER FOR NOT FOUND SET seed_existing_course = NULL;
            SELECT `course_id`, `status`, `question_count`, `total_score`
            INTO seed_existing_course, seed_existing_status, seed_existing_count, seed_existing_total
            FROM `exams` WHERE `id` = seed_exam FOR UPDATE;
        END;

        IF seed_existing_course IS NOT NULL THEN
            -- 已发布快照不可重建；正常重跑只保留已有完整试卷，归档状态也保留。
            IF seed_existing_course <> seed_course
                OR seed_existing_status NOT IN ('published', 'archived')
                OR seed_existing_count <> 10 OR seed_existing_total <> 100
                OR (SELECT COUNT(*) FROM `exam_questions` WHERE `exam_id` = seed_exam) <> 10
                OR (SELECT COUNT(*) FROM `exam_questions` eq
                    JOIN JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                        `id` VARCHAR(64) PATH '$.id',
                        `exam_id` VARCHAR(64) PATH '$.exam_id',
                        `course_id` VARCHAR(64) PATH '$.course_id'
                    )) AS sq ON sq.`id` = eq.`question_id`
                        AND sq.`exam_id` = eq.`exam_id` AND sq.`course_id` = eq.`course_id`
                    WHERE eq.`exam_id` = seed_exam AND JSON_TYPE(eq.`snapshot`) = 'OBJECT') <> 10
            THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Existing demo exam conflicts or is incomplete; no data overwritten';
            END IF;
        ELSE
            -- 不接管已有同名题目或选项，以免改变其他试卷正在使用的题库。
            IF EXISTS (
                SELECT 1 FROM `questions` q
                JOIN JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                    `id` VARCHAR(64) PATH '$.id', `course_id` VARCHAR(64) PATH '$.course_id'
                )) AS sq ON sq.`id` = q.`id`
                WHERE sq.`course_id` = seed_course
            ) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo question id already exists without its seeded exam';
            END IF;
            IF EXISTS (
                SELECT 1 FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                    `course_id` VARCHAR(64) PATH '$.course_id',
                    NESTED PATH '$.options[*]' COLUMNS (`option_id` VARCHAR(64) PATH '$.id')
                )) AS sq
                JOIN `question_options` qo ON qo.`id` = sq.`option_id`
                WHERE sq.`course_id` = seed_course
            ) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo option id already exists without its seeded exam';
            END IF;
            IF (SELECT COUNT(*) FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                    `course_id` VARCHAR(64) PATH '$.course_id',
                    `knowledge_point_id` VARCHAR(64) PATH '$.knowledge_point_id'
                )) AS sq
                JOIN `knowledge_points` kp ON kp.`id` = sq.`knowledge_point_id`
                    AND kp.`course_id` = sq.`course_id` AND kp.`status` = 'active'
                WHERE sq.`course_id` = seed_course) <> 10
            THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Missing active knowledge points for demo course; run course seed first';
            END IF;

            -- 父记录先插入，随后插入选项、知识点关联和试卷题目。
            INSERT INTO `questions`
                (`id`, `course_id`, `kind`, `stem`, `explanation`, `status`, `created_at`, `updated_at`)
            SELECT sq.`id`, sq.`course_id`, sq.`kind`, sq.`stem`, sq.`explanation`, 'active', seed_now, seed_now
            FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                `id` VARCHAR(64) PATH '$.id', `course_id` VARCHAR(64) PATH '$.course_id',
                `kind` VARCHAR(20) PATH '$.kind', `stem` VARCHAR(2000) PATH '$.stem',
                `explanation` VARCHAR(2000) PATH '$.explanation'
            )) AS sq WHERE sq.`course_id` = seed_course;

            INSERT INTO `question_options` (`id`, `question_id`, `label`, `text`, `is_correct`, `sort_order`)
            SELECT sq.`option_id`, sq.`question_id`, sq.`label`, sq.`text`, sq.`is_correct`, sq.`position` - 1
            FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                `question_id` VARCHAR(64) PATH '$.id', `course_id` VARCHAR(64) PATH '$.course_id',
                NESTED PATH '$.options[*]' COLUMNS (
                    `position` FOR ORDINALITY,
                    `option_id` VARCHAR(64) PATH '$.id', `label` VARCHAR(2) PATH '$.label',
                    `text` VARCHAR(2000) PATH '$.text', `is_correct` TINYINT PATH '$.is_correct' ERROR ON ERROR
                )
            )) AS sq WHERE sq.`course_id` = seed_course;

            INSERT INTO `question_knowledge_points` (`question_id`, `knowledge_point_id`, `course_id`)
            SELECT sq.`id`, sq.`knowledge_point_id`, sq.`course_id`
            FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                `id` VARCHAR(64) PATH '$.id', `course_id` VARCHAR(64) PATH '$.course_id',
                `knowledge_point_id` VARCHAR(64) PATH '$.knowledge_point_id'
            )) AS sq WHERE sq.`course_id` = seed_course;

            INSERT INTO `exams`
                (`id`, `course_id`, `title`, `status`, `duration_seconds`, `question_count`, `total_score`,
                 `knowledge_snapshot`, `created_at`, `updated_at`)
            VALUES (seed_exam, seed_course, seed_title, 'draft', 1800, 0, 0, JSON_ARRAY(), seed_now, seed_now);

            -- 与 publish_exam 相同结构；JSON options 保留布尔值，不将 true/false 转为字符串。
            INSERT INTO `exam_questions` (`exam_id`, `question_id`, `course_id`, `sort_order`, `score`, `snapshot`)
            SELECT sq.`exam_id`, sq.`id`, sq.`course_id`, sq.`sort_order`, 10.00,
                JSON_OBJECT('id', sq.`id`, 'kind', sq.`kind`, 'stem', sq.`stem`,
                    'explanation', sq.`explanation`,
                    'options', JSON_EXTRACT(seed_questions, CONCAT('$[', sq.`row_number` - 1, '].options')),
                    'knowledge_points', JSON_ARRAY(JSON_OBJECT('id', kp.`id`, 'name', kp.`name`, 'status', kp.`status`)))
            FROM JSON_TABLE(seed_questions, '$[*]' COLUMNS (
                `row_number` FOR ORDINALITY,
                `id` VARCHAR(64) PATH '$.id', `course_id` VARCHAR(64) PATH '$.course_id',
                `exam_id` VARCHAR(64) PATH '$.exam_id', `knowledge_point_id` VARCHAR(64) PATH '$.knowledge_point_id',
                `kind` VARCHAR(20) PATH '$.kind', `stem` VARCHAR(2000) PATH '$.stem',
                `explanation` VARCHAR(2000) PATH '$.explanation', `sort_order` INT PATH '$.sort_order'
            )) AS sq
            JOIN `knowledge_points` kp ON kp.`id` = sq.`knowledge_point_id` AND kp.`course_id` = sq.`course_id`
            WHERE sq.`course_id` = seed_course;

            -- 冻结课程全部 active 知识点目录，包括当前试卷未覆盖的点。
            UPDATE `exams`
            SET `question_count` = 10, `total_score` = 100.00,
                `knowledge_snapshot` = (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', kp.`id`, 'name', kp.`name`))
                    FROM `knowledge_points` kp WHERE kp.`course_id` = seed_course AND kp.`status` = 'active'),
                `status` = 'published', `updated_at` = seed_now
            WHERE `id` = seed_exam;
        END IF;
        SET seed_index = seed_index + 1;
    END WHILE;

    COMMIT;
END$$
DELIMITER ;

CALL `seed_demo_teacher_questions_exams`();
DROP PROCEDURE `seed_demo_teacher_questions_exams`;

-- 核验：两行，每份试卷 question_count / actual_question_count / snapshot_count 均为 10，总分 100。
SELECT e.`id`, e.`title`, c.`name` AS `course_name`, c.`teacher_id`, e.`status`, e.`duration_seconds`,
       e.`question_count`, e.`total_score`,
       (SELECT COUNT(*) FROM `exam_questions` eq WHERE eq.`exam_id` = e.`id`) AS `actual_question_count`,
       (SELECT COUNT(*) FROM `exam_questions` eq
        WHERE eq.`exam_id` = e.`id` AND JSON_TYPE(eq.`snapshot`) = 'OBJECT') AS `snapshot_count`
FROM `exams` e JOIN `courses` c ON c.`id` = e.`course_id`
WHERE e.`id` IN ('demo-exam-ds-teacher-2', 'demo-exam-python-teacher-2')
ORDER BY e.`id`;

-- 核验各题所属课程、知识点、分值、顺序；不展示正确答案。
SELECT eq.`exam_id`, eq.`sort_order`, q.`id` AS `question_id`, q.`kind`, q.`stem`,
       kp.`name` AS `knowledge_point_name`, eq.`score`
FROM `exam_questions` eq JOIN `questions` q ON q.`id` = eq.`question_id`
JOIN `question_knowledge_points` qkp ON qkp.`question_id` = q.`id` AND qkp.`course_id` = eq.`course_id`
JOIN `knowledge_points` kp ON kp.`id` = qkp.`knowledge_point_id` AND kp.`course_id` = qkp.`course_id`
WHERE eq.`exam_id` IN ('demo-exam-ds-teacher-2', 'demo-exam-python-teacher-2')
ORDER BY eq.`exam_id`, eq.`sort_order`;
