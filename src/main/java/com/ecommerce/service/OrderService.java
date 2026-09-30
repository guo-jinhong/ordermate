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

    /**
     * 系统自动取消超时未支付订单。
     * 幂等设计：仅当订单仍为待支付状态时才执行取消并释放库存。
     * 由定时任务调用，多实例并发安全。
     *
     * @return true 表示本次成功取消，false 表示订单已被其他线程/实例处理
     */
    boolean cancelExpiredOrder(Long orderId);
}
