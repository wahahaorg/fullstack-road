package com.example.studytracker.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.studytracker.common.Result;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.service.StudyService;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/study")
@RequiredArgsConstructor
public class StudyController {

    private final StudyService studyService;

    private Long getUserId(HttpServletRequest request) {
        return (Long) request.getAttribute("userId");
    }

    @PostMapping("/start")
    public Result<Long> startStudy(@Valid @RequestBody StudyStartRequest request) {
        return Result.success(studyService.startStudy(request));
    }

    @PostMapping("/end/{recordId}")
    public Result<Void> endStudy(@PathVariable Long recordId) {
        studyService.endStudy(recordId);
        return Result.success();
    }

    @GetMapping("/today")
    public Result<List<StudyRecordVO>> getTodayRecords(HttpServletRequest request) {
        return Result.success(studyService.getTodayRecords(getUserId(request)));
    }

    @GetMapping("/records")
    public Result<Map<String, Object>> getRecords(
        HttpServletRequest request,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "10") int size
    ) {
        IPage<StudyRecordVO> pageResult = studyService.getRecordsPage(getUserId(request), page, size);
        Map<String, Object> map = new HashMap<>();
        map.put("list", pageResult.getRecords());
        map.put("total", pageResult.getTotal());
        map.put("page", pageResult.getCurrent());
        map.put("pageSize", pageResult.getSize());
        return Result.success(map);
    }

    @GetMapping("/statistics")
    public Result<StatisticsVO> getStatistics(HttpServletRequest request) {
        return Result.success(studyService.getStatistics(getUserId(request)));
    }
}
