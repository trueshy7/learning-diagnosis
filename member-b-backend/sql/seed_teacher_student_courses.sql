-- MySQL 8+：用户、课程、章节、知识点和学生选课演示数据。
-- 先启动后端创建模型表，再在目标数据库执行本文件。
-- 默认数据库为 learning_diagnosis；如实际库名不同，请修改下一行。
-- 新账号使用用户提供的原始密码哈希；已存在的账号不修改密码或身份信息。
-- 固定演示 ID，可重复执行；演示课程恢复为 published，学生恢复为 active。
-- 本文件使用临时存储过程进行异常回滚，执行账号需有 CREATE ROUTINE / ALTER ROUTINE / EXECUTE 权限。

USE `learning_diagnosis`;
SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS `seed_demo_teacher_student_courses`;
DELIMITER $$
CREATE PROCEDURE `seed_demo_teacher_student_courses`()
BEGIN
    DECLARE seed_now BIGINT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET seed_now = UNIX_TIMESTAMP();
    START TRANSACTION;

    -- 1. 用户：学生 id=1，教师 id=2。重复执行只保留已有账号。
    INSERT INTO `users` (`id`, `username`, `password_hash`, `email`, `role`)
    VALUES
        (1, 'admin', '147d157244d70d8369df84e65e83f4a8$0ca2d77e6978ae13ab05215ec9c1767b5c85c09bcf68a86898e7ef87f28300ae', '3025535288@qq.com', 'student'),
        (2, 'teacherAdmin', 'af254562679047884fe7f1c49f6a6a4b$2e3abd3bb66b17ae3715e0a37b98273788cfe9f067399c144a5337dadec2feb4', '3421970295@qq.com', 'teacher')
    ON DUPLICATE KEY UPDATE `id` = `id`;

    -- 防止 ID、用户名或邮箱已被其他账号占用时，将课程错误分配给他人。
    IF NOT EXISTS (
        SELECT 1 FROM `users`
        WHERE `id` = 1 AND `username` = 'admin'
          AND `email` = '3025535288@qq.com' AND `role` = 'student'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed student identity does not match user id 1';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM `users`
        WHERE `id` = 2 AND `username` = 'teacherAdmin'
          AND `email` = '3421970295@qq.com' AND `role` = 'teacher'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed teacher identity does not match user id 2';
    END IF;
    IF EXISTS (
        SELECT 1 FROM `courses`
        WHERE `id` IN ('demo-course-ds-teacher-2', 'demo-course-python-teacher-2')
          AND `teacher_id` <> 2
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed course id belongs to another teacher';
    END IF;

    -- 2. 两门课程：固定由教师 id=2 创建，并发布以供学生选课。
    INSERT INTO `courses`
        (`id`, `name`, `description`, `teacher_id`, `status`, `created_at`, `updated_at`)
    VALUES
        ('demo-course-ds-teacher-2', '数据结构基础', '学习栈与队列的基本概念及常用操作。', 2, 'published', seed_now, seed_now),
        ('demo-course-python-teacher-2', 'Python 程序设计基础', '学习变量、基础数据类型、条件判断及循环。', 2, 'published', seed_now, seed_now)
    ON DUPLICATE KEY UPDATE
        `name` = VALUES(`name`),
        `description` = VALUES(`description`),
        `status` = 'published',
        `updated_at` = seed_now;

    -- 3. 每门课程两个章节，共四个章节。
    INSERT INTO `course_chapters`
        (`id`, `course_id`, `name`, `description`, `sort_order`, `created_at`, `updated_at`)
    VALUES
        ('demo-chapter-ds-stack', 'demo-course-ds-teacher-2', '第一章 栈', '理解栈的后进先出特征并掌握基本操作。', 1, seed_now, seed_now),
        ('demo-chapter-ds-queue', 'demo-course-ds-teacher-2', '第二章 队列', '理解队列的先进先出特征并掌握基本操作。', 2, seed_now, seed_now),
        ('demo-chapter-python-types', 'demo-course-python-teacher-2', '第一章 变量与数据类型', '认识变量及 Python 基础数据类型。', 1, seed_now, seed_now),
        ('demo-chapter-python-control', 'demo-course-python-teacher-2', '第二章 流程控制', '学习条件判断与循环结构。', 2, seed_now, seed_now)
    ON DUPLICATE KEY UPDATE
        `name` = VALUES(`name`),
        `description` = VALUES(`description`),
        `sort_order` = VALUES(`sort_order`),
        `updated_at` = seed_now;

    -- 4. 每个章节两个知识点，共八个，章节与课程成对对应。
    INSERT INTO `knowledge_points`
        (`id`, `course_id`, `chapter_id`, `name`, `description`, `sort_order`, `status`)
    VALUES
        ('demo-kp-stack-concept', 'demo-course-ds-teacher-2', 'demo-chapter-ds-stack', '栈的基本概念', '理解后进先出原则，区分栈顶和栈底。', 1, 'active'),
        ('demo-kp-stack-operations', 'demo-course-ds-teacher-2', 'demo-chapter-ds-stack', '栈的基本操作', '掌握入栈、出栈、读取栈顶及判空。', 2, 'active'),
        ('demo-kp-queue-concept', 'demo-course-ds-teacher-2', 'demo-chapter-ds-queue', '队列的基本概念', '理解先进先出原则，区分队头和队尾。', 1, 'active'),
        ('demo-kp-queue-operations', 'demo-course-ds-teacher-2', 'demo-chapter-ds-queue', '队列的基本操作', '掌握入队、出队、读取队头及判空。', 2, 'active'),
        ('demo-kp-python-variables', 'demo-course-python-teacher-2', 'demo-chapter-python-types', '变量与赋值', '理解变量命名和赋值，能够追踪变量值变化。', 1, 'active'),
        ('demo-kp-python-types', 'demo-course-python-teacher-2', 'demo-chapter-python-types', '基础数据类型', '区分整数、浮点数、字符串与布尔值。', 2, 'active'),
        ('demo-kp-python-conditions', 'demo-course-python-teacher-2', 'demo-chapter-python-control', '条件判断', '理解 if、elif、else 分支及条件表达式。', 1, 'active'),
        ('demo-kp-python-loops', 'demo-course-python-teacher-2', 'demo-chapter-python-control', '循环结构', '理解 for 和 while，能够模拟循环执行过程。', 2, 'active')
    ON DUPLICATE KEY UPDATE
        `name` = VALUES(`name`),
        `description` = VALUES(`description`),
        `sort_order` = VALUES(`sort_order`),
        `status` = 'active';

    -- 5. 学生 id=1 选上两门课。已在课记录保留加入时间；退课记录恢复并重设时间。
    INSERT INTO `course_enrollments`
        (`course_id`, `student_id`, `status`, `enrolled_at`, `updated_at`)
    VALUES
        ('demo-course-ds-teacher-2', 1, 'active', seed_now, seed_now),
        ('demo-course-python-teacher-2', 1, 'active', seed_now, seed_now)
    ON DUPLICATE KEY UPDATE
        `enrolled_at` = IF(`status` = 'withdrawn', seed_now, `enrolled_at`),
        `updated_at` = IF(`status` = 'withdrawn', seed_now, `updated_at`),
        `status` = 'active';

    COMMIT;
END$$
DELIMITER ;

CALL `seed_demo_teacher_student_courses`();
DROP PROCEDURE `seed_demo_teacher_student_courses`;

-- 6. 验证结果，不查询或展示密码哈希。
SELECT `id`, `username`, `email`, `role`
FROM `users` WHERE `id` IN (1, 2) ORDER BY `id`;

SELECT c.`id`, c.`name`, c.`status`, c.`teacher_id`,
       (SELECT COUNT(*) FROM `course_chapters` ch WHERE ch.`course_id` = c.`id`) AS `chapter_count`,
       (SELECT COUNT(*) FROM `knowledge_points` kp WHERE kp.`course_id` = c.`id`) AS `knowledge_point_count`,
       (SELECT COUNT(*) FROM `course_enrollments` ce
        WHERE ce.`course_id` = c.`id` AND ce.`status` = 'active') AS `enrollment_count`
FROM `courses` c
WHERE c.`id` IN ('demo-course-ds-teacher-2', 'demo-course-python-teacher-2')
ORDER BY c.`id`;

SELECT ce.`student_id`, u.`username`, c.`name` AS `course_name`, ce.`status`, ce.`enrolled_at`
FROM `course_enrollments` ce
JOIN `users` u ON u.`id` = ce.`student_id`
JOIN `courses` c ON c.`id` = ce.`course_id`
WHERE ce.`student_id` = 1
  AND ce.`course_id` IN ('demo-course-ds-teacher-2', 'demo-course-python-teacher-2')
ORDER BY c.`id`;
