package com.ecommerce.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OrderDTO {
    private Long id;
    private String orderNo;
    private BigDecimal totalAmount;
    private BigDecimal discountAmount;
    private BigDecimal finalAmount;
    private String shippingAddress;
    private String shippingPhone;
    private String shippingName;
    private Integer status;
    private Integer paymentStatus;
    private String paymentMethod;
    private String remark;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private List<OrderItemDTO> items;
}
