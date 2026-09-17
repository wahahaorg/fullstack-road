CREATE DATABASE IF NOT EXISTS study_tracker DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE study_tracker;

DROP TABLE IF EXISTS study_record;
DROP TABLE IF EXISTS user;

CREATE TABLE user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    password VARCHAR(100) NOT NULL COMMENT 'BCrypt 加密密码',
    email VARCHAR(100) COMMENT '联系邮箱',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

CREATE TABLE study_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '所属用户ID',
    project VARCHAR(100) NOT NULL COMMENT '学习项目/课程名称',
    start_time DATETIME NOT NULL COMMENT '学习开始时间',
    end_time DATETIME COMMENT '学习结束时间',
    status VARCHAR(20) NOT NULL DEFAULT 'STUDYING' COMMENT '状态: STUDYING / COMPLETED',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_user_id (user_id),
    INDEX idx_user_date (user_id, start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习记录表';
