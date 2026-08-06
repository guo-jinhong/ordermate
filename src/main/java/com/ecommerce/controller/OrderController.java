package com.ecommerce.controller;

import com.ecommerce.dto.OrderDTO;
import com.ecommerce.dto.CreateOrderDTO;
import com.ecommerce.dto.ApiResponse;
import com.ecommerce.service.OrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.List;

@Tag(name = "Order", description = "Order Management APIs")
@RestController
@RequestMapping("/orders")
@RequiredArgsConstructor
public class OrderController {
    private final OrderService orderService;

    @Operation(summary = "Create a new order")
    @PostMapping
    public ApiResponse<OrderDTO> createOrder(
            Authentication authentication,
            @Valid @RequestBody CreateOrderDTO createOrderDTO) {
        Long userId = (Long) authentication.getPrincipal();
        OrderDTO orderDTO = orderService.createOrder(userId, createOrderDTO);
        return ApiResponse.success(orderDTO, "Order created successfully");
    }

    @Operation(summary = "Get order by ID")
    @GetMapping("/{orderId}")
    public ApiResponse<OrderDTO> getOrder(
            Authentication authentication,
            @PathVariable Long orderId) {
        Long userId = (Long) authentication.getPrincipal();
        OrderDTO orderDTO = orderService.getUserOrderById(userId, orderId);
        return ApiResponse.success(orderDTO);
    }

    @Operation(summary = "Get order by order number")
    @GetMapping("/order-no/{orderNo}")
    public ApiResponse<OrderDTO> getOrderByNo(
            Authentication authentication,
            @PathVariable String orderNo) {
        Long userId = (Long) authentication.getPrincipal();
        OrderDTO orderDTO = orderService.getUserOrderByNo(userId, orderNo);
        return ApiResponse.success(orderDTO);
    }

    @Operation(summary = "Get user's orders")
    @GetMapping
    public ApiResponse<List<OrderDTO>> getUserOrders(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        List<OrderDTO> orders = orderService.getUserOrders(userId);
        return ApiResponse.success(orders);
    }

    @Operation(summary = "Cancel order (only pending orders)")
    @PostMapping("/{orderId}/cancel")
    public ApiResponse<OrderDTO> cancelOrder(
            Authentication authentication,
            @PathVariable Long orderId) {
        Long userId = (Long) authentication.getPrincipal();
        OrderDTO orderDTO = orderService.cancelOrder(userId, orderId);
        return ApiResponse.success(orderDTO, "Order cancelled successfully");
    }

    @Operation(summary = "Confirm payment for order")
    @PostMapping("/{orderId}/pay")
    public ApiResponse<OrderDTO> confirmPayment(
            Authentication authentication,
            @PathVariable Long orderId) {
        Long userId = (Long) authentication.getPrincipal();
        OrderDTO orderDTO = orderService.confirmPayment(userId, orderId);
        return ApiResponse.success(orderDTO, "Payment confirmed");
    }
}
