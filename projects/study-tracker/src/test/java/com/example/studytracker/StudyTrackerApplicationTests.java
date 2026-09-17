package com.example.studytracker;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:mysql://localhost:3306/study_tracker?useSSL=false",
    "spring.datasource.username=root",
    "spring.datasource.password=root"
})
class StudyTrackerApplicationTests {

    @Test
    void contextLoads() {
    }
}
