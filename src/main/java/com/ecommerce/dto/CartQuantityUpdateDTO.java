package com.ecommerce.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class CartQuantityUpdateDTO {
    @NotNull @Min(1)
    private Long cartId;
    @NotNull @Min(1) @Max(99)
    private Integer quantity;
    @Min(1)
    private Integer previousQuantity;
}
