package com.example.studytracker.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.studytracker.entity.StudyRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface StudyRecordMapper extends BaseMapper<StudyRecord> {
    @Select("SELECT * FROM study_record WHERE user_id = #{userId} AND DATE(start_time) = CURDATE() ORDER BY start_time DESC")
    List<StudyRecord> selectTodayRecords(Long userId);
}
