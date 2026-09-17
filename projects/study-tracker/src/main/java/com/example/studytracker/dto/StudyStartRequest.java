package com.example.studytracker.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class StudyStartRequest {
    @NotNull(message = "用户ID不能为空")
    private Long userId;

    @NotBlank(message = "学习项目不能为空")
    private String project;
}
