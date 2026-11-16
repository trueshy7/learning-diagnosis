-- MySQL 8.0.16+；修改目标库名后完整执行。
-- 在停止业务写入的维护窗口执行；DDL 会隐式提交，整份脚本不是一个可回滚事务。
-- 不修改 course_resources 列，不将历史资料伪标为 ready。
-- 字符集/排序规则继承目标数据库，需与 course_resources.id 一致。
USE `learning_diagnosis`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS resource_index_states (
    resource_id VARCHAR(64) NOT NULL,
    resource_version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    indexed_version INTEGER NULL,
    document_id VARCHAR(128) NULL,
    indexed_hash VARCHAR(64) NULL,
    last_error TEXT NULL,
    acknowledged_at BIGINT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (resource_id),
    CONSTRAINT ck_resource_index_status CHECK (status IN ('pending', 'ready', 'failed', 'deleted')),
    CONSTRAINT ck_resource_index_version CHECK (resource_version >= 1),
    CONSTRAINT ck_resource_index_indexed_version CHECK (
        indexed_version IS NULL OR (indexed_version >= 1 AND indexed_version <= resource_version)
    ),
    CONSTRAINT ck_resource_index_ready CHECK (
        status <> 'ready' OR (indexed_version IS NOT NULL AND indexed_version = resource_version
                             AND document_id IS NOT NULL AND indexed_hash IS NOT NULL)
    ),
    CONSTRAINT fk_resource_index_resource FOREIGN KEY (resource_id)
        REFERENCES course_resources(id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 只初始化缺少状态行的历史资料，包括软删除记录；重复执行保留已有索引结果。
START TRANSACTION;
INSERT INTO resource_index_states (resource_id, resource_version, status, updated_at)
SELECT r.id, r.version, 'pending', UNIX_TIMESTAMP()
FROM course_resources AS r
LEFT JOIN resource_index_states AS s ON s.resource_id = r.id
WHERE s.resource_id IS NULL;
COMMIT;

SELECT status, COUNT(*) AS resource_count FROM resource_index_states GROUP BY status;
