package com.ecommerce.service;

import com.ecommerce.dto.OrderDTO;
import com.ecommerce.dto.CreateOrderDTO;
import com.ecommerce.entity.Order;
import org.springframework.data.domain.Page;

import java.util.List;

public interface OrderService {
    OrderDTO createOrder(Long userId, CreateOrderDTO createOrderDTO);
    OrderDTO getOrderById(Long orderId);
    OrderDTO getOrderByNo(String orderNo);
    OrderDTO getUserOrderById(Long userId, Long orderId);
    OrderDTO getUserOrderByNo(Long userId, String orderNo);
    List<OrderDTO> getUserOrders(Long userId);
    Page<OrderDTO> getUserOrders(Long userId, int page, int size);
    OrderDTO updateOrderStatus(Long orderId, Integer status);
    OrderDTO cancelOrder(Long userId, Long orderId);
    OrderDTO confirmPayment(Long userId, Long orderId);
    List<OrderDTO> getAllOrders(Integer status);
    Page<OrderDTO> getAllOrders(Integer status, int page, int size);
    Order getOrderEntityById(Long orderId);
}
