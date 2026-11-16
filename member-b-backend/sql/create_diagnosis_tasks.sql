-- MySQL 8.0.16+；按实际库名修改 USE 后执行。
-- 只创建缺失的诊断通知任务表，不自动为所有历史测验生成任务。
-- DDL 隐式提交。历史测验可由本人学生/所属教师通过 POST diagnosis-task 补建。
-- 外键列的字符集及排序规则须与 exam_attempts.id 一致。
USE `learning_diagnosis`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS diagnosis_tasks (
    id VARCHAR(64) NOT NULL,
    attempt_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at BIGINT NOT NULL,
    lease_token VARCHAR(64) NULL,
    lease_expires_at BIGINT NULL,
    input_snapshot JSON NULL,
    input_hash VARCHAR(64) NULL,
    receipt JSON NULL,
    last_error TEXT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    delivered_at BIGINT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_diagnosis_task_attempt (attempt_id),
    KEY ix_diagnosis_tasks_due (status, next_retry_at),
    KEY ix_diagnosis_tasks_lease (status, lease_expires_at),
    CONSTRAINT fk_diagnosis_task_attempt FOREIGN KEY (attempt_id)
        REFERENCES exam_attempts(id) ON DELETE RESTRICT,
    CONSTRAINT ck_diagnosis_task_status CHECK (status IN ('pending', 'dispatching', 'delivered', 'failed')),
    CONSTRAINT ck_diagnosis_task_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_diagnosis_task_lease CHECK (
        (status = 'dispatching' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR
        (status <> 'dispatching' AND lease_token IS NULL AND lease_expires_at IS NULL)
    ),
    CONSTRAINT ck_diagnosis_task_input CHECK (
        (input_snapshot IS NULL AND input_hash IS NULL) OR
        (input_snapshot IS NOT NULL AND input_hash IS NOT NULL)
    ),
    CONSTRAINT ck_diagnosis_task_receipt CHECK (
        status <> 'delivered' OR (receipt IS NOT NULL AND delivered_at IS NOT NULL)
    )
) ENGINE=InnoDB;
