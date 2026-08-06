package com.ecommerce.service.impl;

import com.ecommerce.dto.OrderDTO;
import com.ecommerce.entity.Order;
import com.ecommerce.entity.OrderItem;
import com.ecommerce.entity.Product;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.OrderItemRepository;
import com.ecommerce.repository.OrderRepository;
import com.ecommerce.service.OrderPaymentService;
import com.ecommerce.service.ProductService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional
public class OrderPaymentServiceImpl implements OrderPaymentService {
    private final OrderRepository orderRepository;
    private final OrderItemRepository orderItemRepository;
    private final ProductService productService;

    @Override
    public OrderDTO confirmPayment(Long orderId) {
        Order order = orderRepository.findByIdForUpdate(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderId));

        if (order.getStatus() != 0) {
            throw new BusinessException("Only pending orders can be paid");
        }

        if (order.getPaymentStatus() == 1) {
            throw new BusinessException("Order already paid");
        }

        order.setPaymentStatus(1);
        order.setPaidAt(LocalDateTime.now());
        order.setStatus(1);

        Order updatedOrder = orderRepository.save(order);
        return OrderDTOConverter.convertToDTO(updatedOrder);
    }

    @Override
    public void initiateRefund(Long orderId) {
        Order order = orderRepository.findByIdForUpdate(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderId));

        if (order.getPaymentStatus() != 1) {
            throw new BusinessException("Only paid orders can be refunded");
        }

        if (order.getPaymentStatus() == 3) {
            throw new BusinessException("Order already refunded");
        }

        order.setPaymentStatus(2);
        orderRepository.save(order);
    }

    @Override
    public OrderDTO completeRefund(Long orderId) {
        Order order = orderRepository.findByIdForUpdate(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderId));

        if (order.getPaymentStatus() != 2) {
            throw new BusinessException("Only orders in refunding status can be completed");
        }

        List<OrderItem> items = orderItemRepository.findByOrderId(orderId);
        for (OrderItem item : items) {
            Product product = productService.getProductEntityForUpdate(item.getProduct().getId());
            product.setStock(product.getStock() + item.getQuantity());
            product.setSoldCount(product.getSoldCount() - item.getQuantity());
        }

        order.setPaymentStatus(3);
        order.setStatus(4);

        Order updatedOrder = orderRepository.save(order);
        return OrderDTOConverter.convertToDTO(updatedOrder);
    }
}
