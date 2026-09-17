package com.example.studytracker.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class StudyRecordVO {
    private Long id;
    private String project;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private Long duration;
    private String status;
}
