package com.ecommerce.controller.admin;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.dto.UserDTO;
import com.ecommerce.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@Tag(name = "Admin - User", description = "User management APIs (admin only)")
@RestController
@RequestMapping("/admin/users")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminUserController {
    private final UserService userService;

    @Operation(summary = "List all users")
    @GetMapping
    public ApiResponse<List<UserDTO>> list() {
        return ApiResponse.success(userService.getAllUsers());
    }

    @Operation(summary = "Get user detail")
    @GetMapping("/{userId}")
    public ApiResponse<UserDTO> get(@PathVariable Long userId) {
        return ApiResponse.success(userService.getUserInfo(userId));
    }

    @Operation(summary = "Enable user (status=1)")
    @PostMapping("/{userId}/enable")
    public ApiResponse<UserDTO> enable(@PathVariable Long userId) {
        return ApiResponse.success(userService.setUserStatus(userId, 1), "User enabled");
    }

    @Operation(summary = "Disable user (status=0)")
    @PostMapping("/{userId}/disable")
    public ApiResponse<UserDTO> disable(@PathVariable Long userId) {
        return ApiResponse.success(userService.setUserStatus(userId, 0), "User disabled");
    }
}
