package com.example.studytracker.common;

import lombok.Getter;

@Getter
public enum ErrorCode {
    SUCCESS(200, "操作成功"),
    BAD_REQUEST(400, "请求参数有误"),
    UNAUTHORIZED(401, "未授权访问"),
    FORBIDDEN(403, "没有访问权限"),
    NOT_FOUND(404, "请求资源未找到"),
    INTERNAL_ERROR(500, "服务器内部异常");

    private final int code;
    private final String message;

    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
}
