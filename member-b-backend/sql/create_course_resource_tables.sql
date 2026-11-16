-- MySQL 8.0.16+：B 的资料正文、知识点关联和原文件元数据，不调用 C/D。
-- 先确保 courses、knowledge_points 已存在且包含当前模型声明的复合唯一键。
-- 如目标数据库名不同，请修改 USE。启动新版后端也会自动创建缺失表。
-- CREATE TABLE IF NOT EXISTS 可重跑，但不修复已有同名表的字段或约束。
-- DDL 会隐式提交，请独立执行；不删除既有业务数据。原文件另存于私有上传目录。

USE `learning_diagnosis`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS course_resources (
	id VARCHAR(64) NOT NULL, 
	course_id VARCHAR(64) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	text MEDIUMTEXT NOT NULL, 
	source VARCHAR(1000) NOT NULL DEFAULT '课程教师自编材料', 
	version INTEGER NOT NULL DEFAULT '1', 
	status VARCHAR(20) NOT NULL DEFAULT 'active', 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_course_resources_course_id UNIQUE (course_id, id), 
	CONSTRAINT ck_course_resources_status CHECK (status IN ('active', 'deleted')), 
	CONSTRAINT ck_course_resources_version CHECK (version >= 1), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE RESTRICT,
	KEY `ix_course_resources_course_status_updated` (`course_id`, `status`, `updated_at`)
)ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resource_knowledge_points (
	resource_id VARCHAR(64) NOT NULL, 
	knowledge_point_id VARCHAR(64) NOT NULL, 
	course_id VARCHAR(64) NOT NULL, 
	PRIMARY KEY (resource_id, knowledge_point_id), 
	CONSTRAINT fk_resource_points_resource FOREIGN KEY(course_id, resource_id) REFERENCES course_resources (course_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_resource_points_point FOREIGN KEY(course_id, knowledge_point_id) REFERENCES knowledge_points (course_id, id) ON DELETE RESTRICT,
	KEY `ix_resource_points_course_point` (`course_id`, `knowledge_point_id`),
	KEY `ix_resource_points_course_resource` (`course_id`, `resource_id`)
)ENGINE=InnoDB;

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

SHOW CREATE TABLE course_resources;
SHOW CREATE TABLE resource_knowledge_points;
SHOW CREATE TABLE resource_files;
