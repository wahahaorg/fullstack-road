package com.example.studytracker.service.impl;

import com.example.studytracker.common.BusinessException;
import com.example.studytracker.dto.LoginRequest;
import com.example.studytracker.dto.RegisterRequest;
import com.example.studytracker.entity.User;
import com.example.studytracker.mapper.UserMapper;
import com.example.studytracker.service.UserService;
import com.example.studytracker.util.JwtUtil;
import com.example.studytracker.vo.LoginResponse;
import com.example.studytracker.vo.UserVO;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {

    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;

    @Override
    public UserVO register(RegisterRequest request) {
        if (userMapper.selectByUsername(request.getUsername()) != null) {
            throw new BusinessException("用户名已存在");
        }
        User user = new User();
        user.setUsername(request.getUsername());
        user.setPassword(passwordEncoder.encode(request.getPassword()));
        user.setEmail(request.getEmail());
        userMapper.insert(user);
        return toVO(user);
    }

    @Override
    public LoginResponse login(LoginRequest request) {
        User user = userMapper.selectByUsername(request.getUsername());
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BusinessException("用户名或密码错误");
        }
        LoginResponse resp = new LoginResponse();
        resp.setToken(jwtUtil.generateToken(user.getId(), user.getUsername()));
        resp.setUserId(user.getId());
        resp.setUsername(user.getUsername());
        return resp;
    }

    private UserVO toVO(User user) {
        UserVO vo = new UserVO();
        vo.setId(user.getId());
        vo.setUsername(user.getUsername());
        vo.setEmail(user.getEmail());
        return vo;
    }
}
