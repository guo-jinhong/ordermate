package com.ecommerce.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ReviewDTO {
    private Long productId;
    
    @NotNull(message = "Rating cannot be null")
    @Min(value = 1, message = "Rating must be at least 1")
    @Max(value = 5, message = "Rating cannot exceed 5")
    private Integer rating;
    
    private String content;
}
