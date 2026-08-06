package com.ecommerce.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.math.BigDecimal;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OrderItemDTO {
    @NotNull(message = "Product ID cannot be null")
    private Long productId;
    private String productName;
    @NotNull(message = "Quantity cannot be null")
    @Min(value = 1, message = "Quantity must be at least 1")
    private Integer quantity;
    private BigDecimal unitPrice;
    private BigDecimal totalPrice;
}
