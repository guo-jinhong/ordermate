package com.ecommerce.service;

import com.ecommerce.dto.UserRegisterDTO;
import com.ecommerce.dto.UserLoginDTO;
import com.ecommerce.dto.UserDTO;
import com.ecommerce.entity.User;
import java.util.List;

public interface UserService {
    UserDTO register(UserRegisterDTO registerDTO);
    String login(UserLoginDTO loginDTO);
    UserDTO getUserInfo(Long userId);
    UserDTO updateUserInfo(Long userId, UserDTO userDTO);
    User getUserById(Long userId);
    User getUserByUsername(String username);

    // ----- admin -----
    List<UserDTO> getAllUsers();
    UserDTO setUserStatus(Long userId, Integer status);
}
