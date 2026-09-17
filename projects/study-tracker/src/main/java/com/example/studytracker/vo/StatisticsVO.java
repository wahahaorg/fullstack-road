package com.example.studytracker.vo;

import lombok.Data;

import java.util.Map;

@Data
public class StatisticsVO {
    private long totalMinutes;
    private int totalRecords;
    private Map<String, Long> projectStats;
}
