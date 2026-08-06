package com.ecommerce.controller;

import com.ecommerce.dto.UserRegisterDTO;
import com.ecommerce.dto.UserLoginDTO;
import com.ecommerce.dto.UserDTO;
import com.ecommerce.dto.ApiResponse;
import com.ecommerce.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

@Tag(name = "User", description = "User Management APIs")
@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class UserController {
    private final UserService userService;

    @Operation(summary = "Register a new user")
    @PostMapping("/register")
    public ApiResponse<UserDTO> register(@Valid @RequestBody UserRegisterDTO registerDTO) {
        UserDTO userDTO = userService.register(registerDTO);
        return ApiResponse.success(userDTO, "User registered successfully");
    }

    @Operation(summary = "Login user")
    @PostMapping("/login")
    public ApiResponse<String> login(@Valid @RequestBody UserLoginDTO loginDTO) {
        String token = userService.login(loginDTO);
        return ApiResponse.success(token, "Login successful");
    }

    @Operation(summary = "Get current user info")
    @GetMapping("/info")
    public ApiResponse<UserDTO> getUserInfo(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        UserDTO userDTO = userService.getUserInfo(userId);
        return ApiResponse.success(userDTO);
    }

    @Operation(summary = "Update user info")
    @PutMapping("/info")
    public ApiResponse<UserDTO> updateUserInfo(
            Authentication authentication,
            @Valid @RequestBody UserDTO userDTO) {
        Long userId = (Long) authentication.getPrincipal();
        UserDTO updatedDTO = userService.updateUserInfo(userId, userDTO);
        return ApiResponse.success(updatedDTO, "User updated successfully");
    }
}
