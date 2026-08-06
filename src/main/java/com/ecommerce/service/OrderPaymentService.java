package com.ecommerce.service;

import com.ecommerce.dto.OrderDTO;

public interface OrderPaymentService {
    OrderDTO confirmPayment(Long orderId);
    void initiateRefund(Long orderId);
    OrderDTO completeRefund(Long orderId);
}
