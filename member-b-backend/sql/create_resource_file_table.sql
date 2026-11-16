-- 已有资料正文表时，只补原文件元数据表；不修改 course_resources 的既有列。
-- 原文件仍保存到 RESOURCE_UPLOAD_DIR；此脚本不导入文件或资料。
-- 修改目标库名后完整执行；父表 course_resources 必须已存在。
USE `learning_diagnosis`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS resource_files (
	id VARCHAR(64) NOT NULL, 
	resource_id VARCHAR(64) NOT NULL, 
	resource_version INTEGER NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	media_type VARCHAR(100) NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	storage_key VARCHAR(100) NOT NULL, 
	extraction_info JSON NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_resource_files_version CHECK (resource_version >= 1), 
	CONSTRAINT ck_resource_files_size CHECK (size_bytes > 0 AND size_bytes <= 10485760), 
	UNIQUE (resource_id), 
	FOREIGN KEY(resource_id) REFERENCES course_resources (id) ON DELETE RESTRICT, 
	UNIQUE (storage_key)
)ENGINE=InnoDB;

SHOW CREATE TABLE resource_files;
