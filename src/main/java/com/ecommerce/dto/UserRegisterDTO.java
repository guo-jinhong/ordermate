package com.ecommerce.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserRegisterDTO {
    @NotBlank(message = "Username cannot be blank")
    @Size(min = 3, max = 50, message = "Username length must be between 3 and 50")
    private String username;

    @NotBlank(message = "Password cannot be blank")
    @Size(min = 8, max = 100, message = "Password length must be between 8 and 100")
    @Pattern(regexp = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>\\/?]).+$",
            message = "Password must contain at least one uppercase letter, one lowercase letter, one digit, and one special character")
    private String password;

    @NotBlank(message = "Email cannot be blank")
    @Email(message = "Email should be valid")
    private String email;

    private String phone;

    private String realName;
}