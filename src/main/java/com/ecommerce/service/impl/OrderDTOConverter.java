package com.ecommerce.service.impl;

import com.ecommerce.dto.OrderDTO;
import com.ecommerce.dto.OrderItemDTO;
import com.ecommerce.entity.Order;
import java.util.List;
import java.util.stream.Collectors;

public class OrderDTOConverter {
    public static OrderDTO convertToDTO(Order order) {
        if (order == null) {
            return null;
        }

        List<OrderItemDTO> items = order.getOrderItems().stream()
                .map(item -> OrderItemDTO.builder()
                        .productId(item.getProduct().getId())
                        .productName(item.getProduct().getName())
                        .quantity(item.getQuantity())
                        .unitPrice(item.getUnitPrice())
                        .totalPrice(item.getTotalPrice())
                        .build())
                .collect(Collectors.toList());

        return OrderDTO.builder()
                .id(order.getId())
                .orderNo(order.getOrderNo())
                .totalAmount(order.getTotalAmount())
                .discountAmount(order.getDiscountAmount())
                .finalAmount(order.getFinalAmount())
                .shippingAddress(order.getShippingAddress())
                .shippingPhone(order.getShippingPhone())
                .shippingName(order.getShippingName())
                .status(order.getStatus())
                .paymentStatus(order.getPaymentStatus())
                .paymentMethod(order.getPaymentMethod())
                .remark(order.getRemark())
                .createdAt(order.getCreatedAt())
                .updatedAt(order.getUpdatedAt())
                .items(items)
                .build();
    }
}
