package com.ecommerce.service;

import com.ecommerce.dto.UserDTO;
import com.ecommerce.dto.UserLoginDTO;
import com.ecommerce.dto.UserRegisterDTO;
import com.ecommerce.entity.User;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.UserRepository;
import com.ecommerce.service.impl.UserServiceImpl;
import com.ecommerce.util.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private JwtTokenProvider jwtTokenProvider;

    @InjectMocks
    private UserServiceImpl userService;

    private UserRegisterDTO registerDTO;
    private User existingUser;

    @BeforeEach
    void setUp() {
        registerDTO = UserRegisterDTO.builder()
                .username("alice")
                .password("secret123")
                .email("alice@example.com")
                .phone("13800000001")
                .realName("Alice")
                .build();

        existingUser = User.builder()
                .id(1L)
                .username("alice")
                .password("hashed")
                .email("alice@example.com")
                .status(1)
                .role(0)
                .build();
    }

    @Test
    void register_success() {
        when(userRepository.existsByUsername("alice")).thenReturn(false);
        when(userRepository.existsByEmail("alice@example.com")).thenReturn(false);
        when(passwordEncoder.encode("secret123")).thenReturn("hashed");
        when(userRepository.save(any(User.class))).thenAnswer(inv -> {
            User u = inv.getArgument(0);
            u.setId(1L);
            return u;
        });

        UserDTO dto = userService.register(registerDTO);

        assertThat(dto.getId()).isEqualTo(1L);
        assertThat(dto.getUsername()).isEqualTo("alice");
        verify(userRepository).save(any(User.class));
    }

    @Test
    void register_duplicateUsername_throws() {
        when(userRepository.existsByUsername("alice")).thenReturn(true);

        assertThatThrownBy(() -> userService.register(registerDTO))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("Username");
        verify(userRepository, never()).save(any());
    }

    @Test
    void register_duplicateEmail_throws() {
        when(userRepository.existsByUsername("alice")).thenReturn(false);
        when(userRepository.existsByEmail("alice@example.com")).thenReturn(true);

        assertThatThrownBy(() -> userService.register(registerDTO))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("Email");
    }

    @Test
    void login_success_returnsToken() {
        UserLoginDTO login = UserLoginDTO.builder().username("alice").password("secret123").build();
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(existingUser));
        when(passwordEncoder.matches("secret123", "hashed")).thenReturn(true);
        when(jwtTokenProvider.generateToken(eq(1L), eq("alice"), eq(0))).thenReturn("jwt-token");

        String token = userService.login(login);

        assertThat(token).isEqualTo("jwt-token");
    }

    @Test
    void login_wrongPassword_throws() {
        UserLoginDTO login = UserLoginDTO.builder().username("alice").password("wrong").build();
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(existingUser));
        when(passwordEncoder.matches(anyString(), anyString())).thenReturn(false);

        assertThatThrownBy(() -> userService.login(login))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void login_disabledAccount_throws() {
        existingUser.setStatus(0);
        UserLoginDTO login = UserLoginDTO.builder().username("alice").password("secret123").build();
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(existingUser));
        when(passwordEncoder.matches(anyString(), anyString())).thenReturn(true);

        assertThatThrownBy(() -> userService.login(login))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("disabled");
    }

    @Test
    void getUserById_notFound_throws() {
        when(userRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> userService.getUserById(99L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void setUserStatus_cannotDisableAdmin() {
        User admin = User.builder().id(2L).username("admin").role(1).status(1).build();
        when(userRepository.findById(2L)).thenReturn(Optional.of(admin));

        assertThatThrownBy(() -> userService.setUserStatus(2L, 0))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("admin");
    }

    @Test
    void setUserStatus_disablesRegularUser() {
        when(userRepository.findById(1L)).thenReturn(Optional.of(existingUser));
        when(userRepository.save(any(User.class))).thenAnswer(inv -> inv.getArgument(0));

        UserDTO dto = userService.setUserStatus(1L, 0);

        assertThat(dto.getStatus()).isEqualTo(0);
    }
}
