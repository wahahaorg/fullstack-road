package com.example.studytracker.service;

import com.example.studytracker.dto.LoginRequest;
import com.example.studytracker.dto.RegisterRequest;
import com.example.studytracker.vo.LoginResponse;
import com.example.studytracker.vo.UserVO;

public interface UserService {
    UserVO register(RegisterRequest request);
    LoginResponse login(LoginRequest request);
}
