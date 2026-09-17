package com.example.studytracker.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;

import java.util.List;

public interface StudyService {
    Long startStudy(StudyStartRequest request);
    void endStudy(Long recordId);
    List<StudyRecordVO> getTodayRecords(Long userId);
    IPage<StudyRecordVO> getRecordsPage(Long userId, int pageNum, int pageSize);
    StatisticsVO getStatistics(Long userId);
}
