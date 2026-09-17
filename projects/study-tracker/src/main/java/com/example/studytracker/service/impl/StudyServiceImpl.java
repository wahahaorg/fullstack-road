package com.example.studytracker.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.studytracker.common.BusinessException;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.entity.StudyRecord;
import com.example.studytracker.mapper.StudyRecordMapper;
import com.example.studytracker.service.StudyService;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class StudyServiceImpl implements StudyService {

    private final StudyRecordMapper studyRecordMapper;

    @Override
    public Long startStudy(StudyStartRequest request) {
        StudyRecord record = new StudyRecord();
        record.setUserId(request.getUserId());
        record.setProject(request.getProject());
        record.setStartTime(LocalDateTime.now());
        record.setStatus("STUDYING");
        studyRecordMapper.insert(record);
        log.info("用户 {} 开始学习 {}", request.getUserId(), request.getProject());
        return record.getId();
    }

    @Override
    public void endStudy(Long recordId) {
        StudyRecord record = studyRecordMapper.selectById(recordId);
        if (record == null) {
            throw new BusinessException("学习记录不存在");
        }
        if (!"STUDYING".equals(record.getStatus())) {
            throw new BusinessException("该学习记录已结束或状态异常");
        }
        record.setEndTime(LocalDateTime.now());
        record.setStatus("COMPLETED");
        studyRecordMapper.updateById(record);
        log.info("学习记录 {} 结束打卡", recordId);
    }

    @Override
    public List<StudyRecordVO> getTodayRecords(Long userId) {
        return studyRecordMapper.selectTodayRecords(userId).stream()
            .map(this::toVO)
            .collect(Collectors.toList());
    }

    @Override
    public IPage<StudyRecordVO> getRecordsPage(Long userId, int pageNum, int pageSize) {
        Page<StudyRecord> page = new Page<>(pageNum, pageSize);
        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .orderByDesc(StudyRecord::getStartTime);
        IPage<StudyRecord> recordPage = studyRecordMapper.selectPage(page, wrapper);

        Page<StudyRecordVO> voPage = new Page<>(pageNum, pageSize, recordPage.getTotal());
        voPage.setRecords(recordPage.getRecords().stream().map(this::toVO).collect(Collectors.toList()));
        return voPage;
    }

    @Override
    public StatisticsVO getStatistics(Long userId) {
        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .eq(StudyRecord::getStatus, "COMPLETED")
               .isNotNull(StudyRecord::getEndTime);
        List<StudyRecord> records = studyRecordMapper.selectList(wrapper);

        Map<String, Long> projectStats = records.stream()
            .collect(Collectors.groupingBy(StudyRecord::getProject,
                Collectors.summingLong(r -> Duration.between(r.getStartTime(), r.getEndTime()).toMinutes())));

        long totalMinutes = records.stream()
            .mapToLong(r -> Duration.between(r.getStartTime(), r.getEndTime()).toMinutes())
            .sum();

        StatisticsVO vo = new StatisticsVO();
        vo.setTotalMinutes(totalMinutes);
        vo.setTotalRecords(records.size());
        vo.setProjectStats(projectStats);
        return vo;
    }

    private StudyRecordVO toVO(StudyRecord r) {
        StudyRecordVO vo = new StudyRecordVO();
        vo.setId(r.getId());
        vo.setProject(r.getProject());
        vo.setStartTime(r.getStartTime());
        vo.setEndTime(r.getEndTime());
        vo.setStatus(r.getStatus());
        if (r.getEndTime() != null) {
            vo.setDuration(Duration.between(r.getStartTime(), r.getEndTime()).toMinutes());
        }
        return vo;
    }
}
