-- MySQL 8+：补齐旧 exam_attempts 表缺失的 knowledge_snapshot。
-- 对应症状：开始测验返回 503，数据库原始错误为 1054 Unknown column ...knowledge_snapshot。
-- 请先确认目标库；如数据库名称不同，修改下一行 USE。
-- 不删除作答、答案或成绩；只补缺失列，并从其所属试卷回填 SQL NULL。
-- 已有非 NULL 快照保留，可重复执行。账号需要 ALTER、SELECT、UPDATE 及存储过程权限。
-- MySQL 的 ALTER TABLE 会隐式提交；本文件不是可整体回滚的 DDL 事务。

USE `learning_diagnosis`;

DROP PROCEDURE IF EXISTS `repair_exam_attempt_knowledge_snapshot`;
DELIMITER $$
CREATE PROCEDURE `repair_exam_attempt_knowledge_snapshot`()
BEGIN
    DECLARE snapshot_exists INT DEFAULT 0;
    DECLARE snapshot_type VARCHAR(64);
    DECLARE snapshot_nullable VARCHAR(3);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = 'exam_attempts'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'exam_attempts is missing; start current backend to create tables first';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'exams'
          AND column_name = 'knowledge_snapshot' AND data_type = 'json'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'exams.knowledge_snapshot JSON column is required before this repair';
    END IF;

    SELECT COUNT(*) INTO snapshot_exists FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'exam_attempts'
      AND column_name = 'knowledge_snapshot';

    IF snapshot_exists = 0 THEN
        -- 先验证历史记录能找到有效目录，再执行补列。
        IF EXISTS (
            SELECT 1 FROM exam_attempts a LEFT JOIN exams e
                ON e.id = a.exam_id AND e.course_id = a.course_id
            WHERE e.id IS NULL OR COALESCE(JSON_TYPE(e.knowledge_snapshot), 'NULL') <> 'ARRAY'
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'An existing attempt has no valid exam knowledge snapshot; inspect history first';
        END IF;
        ALTER TABLE exam_attempts ADD COLUMN knowledge_snapshot JSON NULL AFTER total_score;
    END IF;

    SELECT data_type, is_nullable INTO snapshot_type, snapshot_nullable
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'exam_attempts'
      AND column_name = 'knowledge_snapshot';
    IF snapshot_type <> 'json' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Existing attempt knowledge_snapshot is not JSON; no type conversion performed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM exam_attempts a LEFT JOIN exams e
            ON e.id = a.exam_id AND e.course_id = a.course_id
        WHERE a.knowledge_snapshot IS NULL
          AND (e.id IS NULL OR COALESCE(JSON_TYPE(e.knowledge_snapshot), 'NULL') <> 'ARRAY')
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot backfill a NULL snapshot from its exam; inspect history first';
    END IF;

    START TRANSACTION;
    UPDATE exam_attempts a JOIN exams e ON e.id = a.exam_id AND e.course_id = a.course_id
    SET a.knowledge_snapshot = e.knowledge_snapshot
    WHERE a.knowledge_snapshot IS NULL;
    COMMIT;

    IF snapshot_nullable = 'YES' THEN
        ALTER TABLE exam_attempts MODIFY COLUMN knowledge_snapshot JSON NOT NULL;
    END IF;
END$$
DELIMITER ;

CALL `repair_exam_attempt_knowledge_snapshot`();
DROP PROCEDURE `repair_exam_attempt_knowledge_snapshot`;

-- 应返回一行：knowledge_snapshot / json / NO。
SELECT column_name, data_type, is_nullable FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'exam_attempts'
  AND column_name = 'knowledge_snapshot';
