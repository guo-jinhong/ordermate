package com.ecommerce.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CreateOrderDTO {
    @NotNull(message = "Address ID cannot be null")
    private Long addressId;

    @NotBlank(message = "Payment method cannot be blank")
    private String paymentMethod;

    private String remark;

    // 同一购买意图的服务端幂等键，允许旧客户端不传。
    @Pattern(regexp = "[A-Za-z0-9_-]{16,128}")
    private String idempotencyKey;

    @NotEmpty(message = "Order must contain at least one item")
    @Valid
    private List<OrderItemDTO> items;
}
